# Mutation portability research and proposed integer operator

Reviewed 2026-10-12. PAPER-COMPACT-03B3C2B1 completes the offline compatibility
experiment and a separately versioned operator prototype. The full03B3C2B gate
stays open: this proposal is not installed in the GA model, independent complete
transition validator, native package, checkpoint decoder or hosted worker.

## Finding and its limits

The current GA uses CPython `random.gauss`, then clamps and rounds the two EMA
periods. The pinned [CPython3.12.14 implementation](https://github.com/python/cpython/blob/v3.12.14/Lib/random.py)
forms first/cached Gaussian variates using trigonometry, logarithm and square root.
Python's [math documentation](https://docs.python.org/3.12/library/math.html)
describes platform C math functions. PostgreSQL's [mathematical function documentation](https://www.postgresql.org/docs/17/functions-math.html)
likewise explains that many floating-point functions use the host C library and
can differ at boundaries. Matching MT19937 state and draws alone does not prove
that the final integer phenotype is identical across these implementations.

The reproducible experiment compares macOS arm64 CPython3.12.14 against the pinned
owned Linux PostgreSQL17.6 image. It follows the legacy operation order, both
first/cached variates, actual binary64 strengths (`0.15*9` and `0.15*45`), clamps
and nearest-half-up conversion. Inputs are on the53-bit uniform grid. The random
profile includes4096 random cases and756 constructed boundaries. The second
profile constructs adjacent grid points around rounding boundaries using128
angles per period/cached combination.

| Profile | Cases | Different noise bits | Different integer periods |
| --- | ---: | ---: | ---: |
| Random plus initial boundaries | 4,852 | 111 | 0 |
| Targeted adjacent rounding boundaries | 71,582 | 4,612 | 145 |

For one constructed fast-period input, both start at12 with angle uniform
`0.3734184904561133`, radius uniform `0.9697689883942827` and strength
`1.3499999999999999`; Python yields9 while PostgreSQL yields10. The artifacts
retain exact inputs and noise bits for representative mismatches.

These are **synthetic uniform inputs**, not a corpus of accepted commands or a
proof that a configured namespaced seed reaches a mismatch. Counts are not
production failure rates. The Linux worker's Python math library was not compared
here. The experiment does establish that straightforward PostgreSQL Gaussian
substitution cannot be assumed equivalent to the tested macOS reference.
Tolerance would allow a different genome and is not an exact validation repair.

The [random-profile artifact](research/gaussian-compatibility-measurements.json)
and [boundary artifact](research/gaussian-boundary-measurements.json) bind the
actual Python/platform, database image and reproducer source hash. Reproduce with
the isolated locked environment, repository PYTHONPATH and
`DASHBOARD_ISOLATED_POSTGRES_TESTS=1`, using
`python -m tests.measure_gaussian_compatibility random` or `boundaries`.
Only an owned fixture is created; no network, ports, application mounts or secrets
are attached. Its temporary math function and container disappear on cleanup.

## Proposed portable operator

`ema-period-triangular-integer-research-v1` is independently implemented in Python
and private research SQL. It keeps fast3–12, slow15–60 and the same per-child
SHA256 mutation namespace for matched-seed comparisons. Only integer operations
determine the decision and output:

1. Consume two MT19937 words to form the53-bit uniform numerator. Compare
   `numerator*1000000 < rate*2**53`, with integer rate200000 for sexual offspring
   and300000 for asexual offspring. No floating-point probability comparison.
2. On mutation, draw two independent uniform bounded integers. Use their
   difference as the step: radius3 for fast and15 for slow. A zero step is valid.
3. Clamp the integer sum to the reviewed period limits. No Gaussian, cached
   variate, floating-point arithmetic or rounding function is needed.

The unclamped step has a symmetric triangular distribution, with variance2.5
for fast and42.5 for slow. Those correspond to standard deviations about1.58 and
6.52, compared with the legacy Gaussian1.35 and6.75. Clamping adds probability
mass at the boundaries. The radii are an initial proposal, not calibrated optimal
values or evidence of trading performance. The proposal omits the legacy
always-consumed fixed-asset mutation draw; its distribution and draw consumption
are deliberately different and require the new operator/model version.

Plain integer type/bounds, canonical uint64 search seed, explicit boolean,
epoch/event through2**31−1, child0–7,256 rejection attempts and2048 total word
draws are bounded. SQL uses exact numeric multiplication for the53-bit rate
comparison to avoid bigint overflow. Fixed controls and single SOL/USD asset
remain outside this proposal's function; complete model validation must bind them.

## Actual validation and isolation

Three actual SQL tests pass. 4,128 complete Python/SQL traces cover129 seed
profiles, two epoch/event pairs, eight children, both mating modes and alternating
period limits. They include982 fast mutation decisions,1030 slow decisions,
869 negative steps,795 positive steps and865 clamped outputs. Another16 traces
match at the maximum counters and interior periods. Equality includes decisions,
draw counts, both bounded draws, deltas and resulting periods. Invalid seeds,
types/bounds and counters fail. Browser/authenticated/service-role/relay/auditor
execution is denied; only the owned limited fixture installer can call the helper.
The offline installation guard is mandatory. No durable rows or production grants
are introduced. [Source-bound measurement artifact](research/portable-period-mutation-measurements.json).

This is bounded test evidence, not an exhaustive RNG proof. It builds on03B3C2A's
independently tested namespace, integer MT19937 and rejection primitives. Native
mutation, complete-model integration and restoration authority remain false.
The installed production package and legacy model are unchanged.

## Ordered implementation and deeper research

1. Integrate this proposal under an explicit new two-EMA model/configuration and
   operator version, preserving old checkpoints, evidence and byte semantics.
   Bind complete configuration/strategy/search/software counters and version
   headers. Do not trust an arbitrary historical prior; use fresh genesis or a
   fully validated semantic chain. Keep the same founders and fixed controls.
2. Independently derive every completed offspring in the composed SQL validator.
   Reject changed in-range periods even when all mirrors and lineage agree.
   Prove real multi-window replacements, sexual/asexual branches, restart,
   interruption, ordinary commands and original strategy draw continuation.
   Close03B3C2B only after the entire transition gate and Stop/resource bounds pass.
3. Complete03 atomic journal/receipt/ID/pins/history/final source/lease integration,
   then04 exact next-wire restoration and05 retention/closed hosted acceptance.
   Prepare forward migration, validation and rollback before hosted installation.
4. Deep substantial research: run actual pinned Linux worker/SQL comparisons,
   investigate reachable legacy boundary seeds if retaining the Gaussian model,
   and measure full validator/resource tails. Compare proposed radii and mutation
   rates under matched seeds, equal data/budgets, grid/random/cash/buy-and-hold
   baselines and held-out longer windows. Examine clamping bias, duplicate/no-op
   offspring, exploration/diversity, activity/objective bias and multiple testing
   before gene expansion. Mechanical portability is not profitability evidence.

The worker remains closed. No hosted schema/data/migration, Railway variables or
deployment, paid market call, wallet/signing/swap or live trading changes are part
of this research. Rollback is a reviewed code/docs revert; no hosted objects exist.
