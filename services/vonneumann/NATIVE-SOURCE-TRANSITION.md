# Independent source and exact indicator validation

Reviewed 2026-10-11. PAPER-COMPACT-03B3B1 is an offline proof for the separately
versioned GA provider model and thirteen-slot compact format. It is not a
production migration, a native command, a checkpoint decoder or a trading lease.
03B3B2 still gates independent causal trading and risk/lifecycle replay.

## What is enforced

The private source validator composes the03B3A economic/allocated-identity
validator and03B2 locked prior/dependency resolver. It independently checks:

- The exact source policy, SOL/USD mint/denomination, epoch, reserved bigint
  sequence ceiling, bootstrap shape and every accepted quote's next sequence.
- Canonical provider request method, endpoint, parameter shape/range, ordered
  distinct32-byte base58 mints and request SHA256. The ordinary provider request
  hash is reconstructed with raw integer timestamps, separately from the tagged
  compact numeric wire; JSONB display text is not used as its canonical hash.
- Original document manifest provider/parser/response size/digest shape and
  receipt clocks. Wall and monotonic receipt ages must both be nonnegative and
  strictly below five seconds. Future tolerance is two seconds and source age
  is at most thirty seconds, including elapsed monotonic time and carried age.
- Strictly increasing provider block references, nondecreasing estimated source
  time/wall receipts and strictly increasing monotonic receipts. The prior age
  floor cannot be erased by a freshly received response with the same estimate.
- Original canonical UTC decision clocks, exact integer microseconds and the
  ceiling of the binary64 monotonic input's exact rational value. No floating
  decimal clock conversion or timestamp-format normalization supplies authority.
- Ordered documents, all-used document indexes, contiguous one-minute records,
  request-range membership, raw/unscaled prices and five-second completion of
  every retained fifteen-minute candle. Complete minute pairs independently
  produce each close/fingerprint. Bootstrap requires61 bars; continuation requires
  the single next bar, retaining at most64. Gaps, revisions and invented hashes fail.
- The exact accepted protective frame for decisions/recovery, phase-eligible
  histories and observation timestamp/price/candle projection. No history is
  ingested while account risk is latched except through reviewed recovery.
- Source-to-engine quote/bar/indicator projection and the exact complete EMA
  state, including count, closes, previous values and current values.

Ordinary control uses no frame or history and keeps source/EMA unchanged. Stop
does not re-age a consumed paid receipt or require a new provider request. Its
canonical current envelope clocks are checked without comparing the unused
monotonic sample to an old frame; model event/control ordering remains checked.
This matches the owned model and preserves Stop with existing holdings.

## Independent indicator arithmetic

The older v5 provider validation path checked warmed indicator shape but did
not independently recompute the seed values. This proof does not modify or
relax that old contract; it closes that gap for the new research format.

All binary64 values are represented as exact integer ratios. An independent
integer quotient/remainder algorithm chooses the binary exponent and rounds
nearest, ties to even, including subnormal values and signed-zero operation
results. It emits canonical hexadecimal tags without a PostgreSQL float cast.
The canonical price string is converted to its indicator value from exact
price units. Each arithmetic operation rounds separately.

For each period2…60 the seed uses the model's scaled mean: convert each price,
choose the maximum scale, individually round division by scale, sum the exact
normalized binary64 ratios and round the sum once, then round division by the
period and multiplication by scale. Later values use separately rounded
previous + (price − previous) × (2 / (period + 1)). The entire previous/current
maps must match, rather than an approximate tolerance or client-supplied hash.

PostgreSQL documents that numeric tie rounding differs from floating-point tie
rounding; integer quotient/remainder makes the desired policy explicit.
[PostgreSQL numeric and floating types](https://www.postgresql.org/docs/17/datatype-numeric.html).
Python documents a possible least-bit fsum discrepancy on some extended-precision
platforms. The proof compares exact results on the isolated CPython3.12 and
pinned PostgreSQL17 fixture; future worker/runtime changes require the same
acceptance rather than widening equality tolerances.
[Python math.fsum](https://docs.python.org/3.12/library/math.html#math.fsum),
[CPython implementation](https://github.com/python/cpython/blob/3.12/Modules/mathmodule.c).

## Evidence trust and remaining boundaries

The versioned source contract explicitly trusts worker-parsed records and
document manifests. Raw external response bytes are absent from this compact
request. A response SHA256 identifies those bytes if retained elsewhere; it
does not authenticate a provider, prove byte retention, or establish that a
parsed value came from that response. A deliberate acceptance test changes
only a response digest and records this boundary. It must not be described as
provider-signed market data or independent raw-body parsing.

The current [Jupiter Price documentation](https://developers.jup.ag/docs/price)
continues to describe the V3 current-price surface. The reviewed research
request remains api.jup.ag/price/v3. This work changes no endpoint, organization
quota, API key or provider setting and makes no paid market call. The historical
minute source remains the separately reviewed OHLCV contract; a latest price
response is not a historical warm-up series.

Source timestamps are worker estimates tied to block references; receipt clocks
are worker evidence within one declared epoch. This proof checks their exact
versioned consistency. Independent server freshness/lease checks at the final
transaction boundary remain native composition work. Hash/shape/source checks
alone cannot decide whether a valid quote actually permits a trade.

03B3B2 must independently derive pending crossing intents, later eligible fills,
protective exits, account/member risk, terminal timing, control/recovery and
restart/replacement behavior.03B3C must independently bind assessments, frozen
metrics, fitness, cohort/optimizer/RNG, selection and actual lineage. The native
composition still must atomically insert original IDs, journal receipts, retain
and pin components and project immutable history before04 restoration and05
retention/closed hosted acceptance.

## Validation and measurements

The actual fixture installs seventeen private functions as a limited synthetic
LOGIN role with no superuser/create-role/create-database/inherit/bypass authority.
All functions pin search_path to pg_catalog, revoke PUBLIC execution and expose
only the final definer wrapper to the fixture auditor. Browser, authenticated,
service-role, relay, direct-helper and table access are rejected. There are no
new durable tables or writes by validation. The pinned owned Docker fixture has
no network, ports, mounts or application credentials and is removed afterward.

The acceptance corpus covers93 complete owned commands across two traded
windows, fractional costs, terminal/risk halt, pause/resume/restart and Stop
with eight holdings. A separate three-command fixture proves a consistently
rehashed frame cannot reset its carried source-age floor.639 independent ratio/
operation cases cover ties, signed zero, subnormal and seeded finite arithmetic.
Eight adversarial price sequences compare all59 warmed periods and seven later
candles, including minimum/maximum permitted prices, near-equal closes and large
alternating moves. Source/indicator mutations fail without changing fixture rows.

Fifteen actual PostgreSQL cases and21 Python capture/partition/canonical/forward
package checks pass. Positive microsecond/monotonic-ceiling and full unsigned64
block-boundary cases pass; overflow, noncanonical clocks and out-of-range blocks
fail. The final installed source SQL SHA256 is
4f1c5b506fa2e9253cd3e7940f9b4d9f429d81561f73a4676ca8db7c3450cede.

Final full-suite results and ten-call warm wrapper measurements are bound to
the installed SQL/image hashes in
[the measurement artifact](research/source-transition-measurements.json).
The wrapper currently resolves dependencies again after economic validation;
the measured work includes that duplication. It is an offline composition proof,
not a selected production optimization. These timings exclude contended waiting,
causal risk/assessment/optimizer/lineage checks, journal/identity/pin/projection
writes, final freshness/lease, COMMIT/WAL, TLS/relay and hosted tails. Ten samples
do not establish a tail-latency guarantee or a viable production command rate.
Warm full-wrapper p95 is839.134ms for bootstrap,313.896ms for a quote,
552.832ms for replacement,551.494ms for risk trip and551.008ms for held Stop.
The duplicated resolver is a concrete composition cost to remove under the same
verified prior lock before drawing cadence or hosting-cost conclusions.

## Deeper research and rollback

1. Prove fsum/rounding acceptance on the exact deployed worker architecture and
   dependency image, with midpoint/near-crossover cases and runtime upgrades.
2. Decide raw-document retention, independent parsing and trust boundaries,
   including request/response binding and practical archive costs. Do not treat
   an unverified digest or a client clock as provider authenticity/server time.
3. Measure complete semantic validation plus contended locks and COMMIT/WAL/TOAST
   tails. Reuse immutable validation only with server-enforced identities and
   pins; a client flag cannot authorize skipping prior/dependency validation.
4. Continue actual source-age/receipt/rate/cost measurements against current
   organization quotas after native admission and closed pilot acceptance.

No Supabase research object, migration, native package/grant, Railway variable/
deployment/capability, archive deletion, billing or live execution changes.
Rollback is a reviewed code/documentation revert with no hosted SQL rollback.
The existing user-owned colonies migration remains excluded and preserved.
