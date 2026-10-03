# Exact provider capture and compatibility views

DB-03A2C2D1 preserves the actual Jupiter Price V3 and Birdeye OHLCV V3 response
bytes before float conversion. Both active paper-feed adapters use this boundary.
Existing controller/indicator interfaces still receive explicit binary64 views;
this does not convert their accounting or make the synthetic v3/v4 exact engine
accept provider data. [Research and remaining questions](EXACT-SOURCE-RESEARCH.md)
record the current primary documentation behind this implementation.

## Captured document and numeric contract

A frozen `ProviderDocument` owns immutable response bytes, the canonical public
GET request, parser policy, receipt wall/monotonic clocks and SHA-256 identities.
Requests pin the provider endpoint and Solana chain and accept only the reviewed
parameter set. Headers, API keys, credential-bearing RPC URLs and arbitrary
query parameters cannot enter the manifest. Raw bytes are omitted from repr and
manifest output; they remain available in the owned in-memory document. No new
disk or database archive, collector, paid acquisition or application retry loop
is introduced. Existing HTTP-client behavior is unchanged; a future transport
must explicitly verify and bound any library-level idempotent retry behavior.

The reader bounds decoded response bytes even without a truthful Content-Length:
128 KiB for Jupiter, 4 MiB for Birdeye. JSON validation rejects duplicate keys,
nonfinite constants, invalid UTF-8, excessive nesting, oversized number tokens,
and unsupported representations. Limits are 32 nesting levels, 200,000 tree
nodes including keys, 128-character numeric tokens, 80 coefficient digits and
exponents from -80 through 80. Canonical consumed monetary values are nonnegative
plain decimal strings with at most 80 integer and 80 fractional digits; prices
must be positive. Conversion does not depend on the ambient Decimal context.

Integers and decimal/exponent tokens are parsed without binary64. The original
literal spelling remains in the raw response; the canonical consumed value is
normalized without rounding. A later economic policy must separately reject
values outside its own grid. This broad capture range is not permission to round
a provider value onto the exact engine's 18-decimal price grid. Token `decimals`
metadata describes token units, never USD-price precision. Exact preservation
also makes no claim about the accuracy of the provider's own computation.

## Quotes, time and cache behavior

`JupiterFeed.get_price_captures` returns immutable document-derived price records
paired with the existing local source-time evidence. Records bind configured
asset/mint, USD reference value, original block reference, optional token decimals,
and document identity. Captures additionally bind the resolved estimated source
time and receipt clocks; malformed or mismatched structural evidence is rejected.
Legacy `get_tick(s)` produces float views from the same validated captures.

The price and exact caches commit only after every requested asset succeeds.
Valid siblings from a field-level failure remain available for the existing
protective pass, without publishing a partial new cache. Invalid JSON, duplicate
keys or nonfinite JSON constants reject the complete response document before
any sibling is treated as validated. External cancellation leaves the new cache
uncommitted. Calling the exact and legacy interfaces within cache validity does
not add a second provider request or refresh receipt clocks.

A caller may mutate a legacy MarketTick, but that cannot alter the retained exact
record or the source-age anchor. Cache validation and refresh-age continuity use
the immutable capture. The original source-age policy still considers both wall
time and elapsed monotonic time, including RPC latency and cache hits.

The resolver policy is explicitly named
`jupiter-block-id-as-slot-estimated-time-v1`: Jupiter documents a block reference,
while Solana getBlockTime consumes a slot. Authoritative mapping/fork semantics
remain a research gate. RPC response bytes are not captured in this increment;
the timestamp is a trusted local resolver result, not Jupiter publication time or
finality. These local monotonic clocks cannot be reused after a process restart.
A digest identifies bytes, not authenticity or permission to reuse old evidence.

## Candles and revision retention

`BirdeyeCandles.get_exact_candles` returns immutable completed-minute records;
JupiterFeed delegates the same interface. The request pins USD price candles,
raw UI amounts, unpadded one-minute ranges and the Solana chain. Records preserve
exact OHLC, token volume, USD volume, open/end times, scaling marker and optional
multiplier. Duplicate rows and OHLC ordering are checked before float conversion,
including malformed excluded boundary rows. Gap/latest-cutoff checks remain in
the adapter. The five-second completion margin is a local rule, not a provider
publication or finality guarantee.

Exact overlapping values and scaling metadata are compared across accepted
requests. Compact fingerprints retain the newest 4,096 accepted minutes per
asset, matching the existing history bound. This detects precision-hidden
revisions when an explicit warmup revisits earlier minutes after narrower
refreshes. Same-cutoff cache reuse now checks whether the original request covered
the wider requested warmup; a narrow incremental cache cannot satisfy it.
Older evicted evidence is not a permanent historical revision archive.
Fingerprints, exact/legacy caches and request watermarks commit together only
after the complete asset batch succeeds. Raw response retention is limited to
currently cached captures; fingerprints do not retain every old document.

Scaled-token source records are preserved for compatibility, with explicit
`require_unscaled()` rejection for a future unscaled profile. This does not
establish cross-provider scaling parity. The first provider-bound exact engine
profile should use a reviewed pinned non-scaled mint, as the research recommends.

## Remaining C2D acceptance

1. Introduce an explicit provider-bound command/source version with SQL validation,
   full source manifests and durable restart watermarks. Do not relabel current
   synthetic v3/v4 commands or feed rounded compatibility values back as exact.
2. Separate market source ordering from decision time: consecutive slots may
   share estimated seconds, while the synthetic planner requires strict time
   advancement. Same-slot changes and equal-time observations need a reviewed
   policy; receipt time cannot silently replace source time.
3. Place planning and submission behind one operational owner. Check freshness
   before planning/submission and again after acknowledgment, reconciliation and
   event delivery. Preparation/capacity/identity failures must close ordinary
   admission while preserving already acknowledged protection and reconciliation.
4. Always install an acknowledged commit even if its evidence expires while
   awaiting the reply. Expiry blocks subsequent economic work; it is not rollback
   evidence and never permits resubmission under a fresh command ID.
5. Prove the active controller follows this ownership path before production
   transport/grant/legacy cutover. Measure parser/cache memory, complete command
   sizes, source-age distributions and protective latency under slow delivery.

This increment does not establish historical availability, provider entitlements,
license/retention permissions beyond the user's existing Jupiter confirmation,
realistic fills, profitable optimization, hosted operation or live execution.
