# Exact provider inputs and source evidence

Research date: **2026-10-02**. This is a design input to DB-03A2C2D, DATA-01,
RES-02 and RES-03. It records public primary documentation, local policy
recommendations and unresolved questions separately. No authenticated provider
requests, dataset purchases, signing, tool installations or account changes were
performed. Read alongside [the prior data decision](JUPITER-DATA-RESEARCH.md)
and [the lifecycle contract](EXACT-LIFECYCLE.md).

## Verified provider contracts

**Jupiter Price V3.** The current OpenAPI defines `usdPrice` and `liquidity` as
JSON numbers, `decimals` as a token-decimal integer, and `blockId` as a nullable
integer. `createdAt` describes token creation, including fixed dates for legacy
tokens; it is not a price-observation timestamp. The schema describes `blockId`
as the Solana block ID at computation, without explicitly defining the RPC slot
mapping. It declares API-key authentication and a maximum of 50 requested mints.
[Current OpenAPI](https://developers.jup.ag/docs/openapi-spec/price/v3/price.yaml).

The overview documents a USD reference derived from qualifying swaps and
heuristics. Requested tokens can be omitted without a per-token error. It says
`blockId` supports recency checks and labels `priceChange24h` as a percentage.
It does not supply an amount-specific execution quote, historical time selector,
or market-data publication timestamp. Its introductory caution mentions nulls,
while its detailed omission contract says missing keys; reject both cases for
an exact tradable observation.
[Price overview](https://developers.jup.ag/docs/price).

**Solana source time.** `getBlockTime` takes an unsigned 64-bit **slot** and
returns estimated production time in Unix seconds, a null when time is unknown,
or an error when the block is unavailable. The estimate is derived from
stake-weighted validator vote timestamps. Its request schema has no explicit
commitment parameter. A successful response does not establish the time Jupiter
published a price or guarantee future immutability.
[RPC contract](https://solana.com/docs/rpc/http/getblocktime).

**Birdeye token OHLCV V3.** The current embedded OpenAPI makes `o/h/l/c/v/v_usd`
JSON numbers and `unix_time` the candle **open** in integer Unix seconds. `v`
is traded token volume; `v_usd` is USD volume. Request parameters distinguish
price from market-cap candles, USD from native denomination, and raw from
scaled UI values. The response distinguishes ordinary fields from `scaled_*`
fields and includes `data.is_scaled_ui_token`. The docs support minute candles,
at most 5,000 rows, range/count modes and unpadded gaps. The endpoint page lists
Standard and higher tiers, but that does not establish this account's actual
access. Two descriptions still conflict: the usage note calls `outlier=false`
unfiltered; the parameter definition describes `true` as allowing outliers.
The reviewed schema does not expose first-publication time or revision identity.
[Endpoint and embedded OpenAPI](https://data.birdeye.so/docs/data-api/price-ohlcv/get-defi-v3-ohlcv).

Solana recommends non-scaled values for internal calculations and provides
separate historical multiplier guidance. Multiplier updates can refer to a past
timestamp, so a current multiplier alone is insufficient for historical
reconstruction. This does not establish how Jupiter's price should be combined
with a scaled token's Birdeye volume.
[Scaled UI integration guide](https://solana.com/docs/tokens/extensions/scaled-ui-amount/integration-guide).

## Recommended bounded implementation

The following are project requirements inferred from those contracts and the
existing exact-accounting design, not provider guarantees.

1. **Decode the wire number before binary64 conversion.** Read a bounded UTF-8
   response and parse numeric lexemes directly into exact decimals/integers.
   Reject duplicate object keys, booleans in numeric fields, quoted numeric
   substitutes, non-finite values, excessive nesting and oversized numeric
   tokens/exponents. A conversion from an already rounded `float` cannot recover
   precision. Preserve an immutable response digest and parser version.

2. **Make the representable range explicit.** Normalize exact values into the
   existing decimal grid only if representable. Reject unsupported precision or
   magnitude rather than rounding silently. Token decimals describe token atomic
   units; do not use them to round a USD price. Exact wire preservation makes no
   claim that the provider's own calculation is mathematically exact.

3. **Bind identity and units.** A manifest should bind chain/mainnet identity,
   mint, local asset label, provider and endpoint versions, request parameters,
   parser/policy versions, response digest, USD denomination and unscaled
   base-token volume. A display label ending in `/USDC` must not reclassify USD
   marks as USDC settlement. Never combine `v` and `v_usd`, or price and
   market-cap candles, under the same history identity.

4. **Start with the established liquid baseline asset.** Keep the first exact
   provider bridge scoped to an explicitly pinned non-scaled mint such as wrapped
   SOL. Reject scaled-token evidence or an unreviewed mint policy. Do not infer
   cross-provider scaling parity from a default parameter or symbol. Broader
   mint/extension support needs its own acceptance evidence.

5. **Separate source, receipt and availability.** Retain the original Jupiter
   block reference, the explicit resolver policy, estimated block time, and local
   receipt wall/monotonic times. Candle start/end are market interval boundaries.
   Local availability begins no earlier than actual receipt, after the chosen
   completion margin. Historical downloads retain today's retrieval time; they
   must not manufacture old live receipts from candle close times.

6. **Persist restart evidence, not process clocks.** Bind accepted source-slot
   and candle watermarks to the immutable command/state. Same-slot observations
   require an explicit policy; lower slots and conflicting repeated candles must
   not silently overwrite history. After restart, old monotonic timestamps are
   unusable: reconcile persisted commands and acquire new evidence before
   admitting ordinary decisions. Retaining a response digest does not authenticate
   the provider or reconstruct a missing original response.

7. **Recheck freshness at consumption boundaries.** Receipt time is not a
   freshness refresh. Use elapsed monotonic time as well as wall/source time so
   clock rollback cannot extend validity. Database acknowledgment, candle fetches,
   event delivery and recovery may consume the allowed lifetime. An acknowledged
   protective transition remains committed even if its observation has since
   expired; ordinary follow-up work must wait for new valid evidence.

8. **Keep preparation failure distinct from no-op success.** If exact decoding,
   protection preparation, identity allocation, payload admission or acknowledgment
   freshness fails, close ordinary admission. Do not reuse an old unconsumed
   checkpoint as if the failed protective phase had completed. Indeterminate
   commits require reconciliation before any new command.

Adversarial fixtures should cover equivalent decimal/exponent forms, values
beyond binary64's exact integer range, excessive exponents/digits, duplicate keys,
null/missing mints, wrong units/scaling, fractional slots/timestamps, future or
regressing evidence, incomplete/revised candles, and stale post-acknowledgment
recovery. Tests must prove rejected evidence leaves source state and watermarks
unchanged. Shared quota/latency and source-age monitoring remain operational
requirements; extra keys do not imply extra capacity.

## Deep research before broader or production admission

- **Jupiter block reference semantics:** obtain an authoritative definition of
  `blockId` as a slot and the provider's fork/update policy. Until then, label the
  current RPC mapping as the application's policy. Research null availability,
  near-tip RPC behavior, time revisions and source-age distributions instead of
  expanding the stale threshold to accommodate failures.
- **Publication and revision:** investigate Birdeye's completion/publication lag,
  outlier contradiction, response changes, gaps and pagination boundaries. The
  current five-second completion margin is a local rule, not a proven SLA or
  historical availability model.
- **Scaling and currency:** verify mint metadata and supported extensions,
  unscaled price/volume parity, historical multipliers, and USD/USDC conversion
  before expanding beyond the pinned baseline.
- **Operational limits:** measure whole-command growth, parser peak memory,
  optimizer/candle history bounds, database lease/acknowledgment latency, event
  backlog and protective scheduling. Do not block the next protective observation
  behind unbounded outbox publication.
- **Research datasets:** resolve separate Birdeye entitlement/retention terms,
  record acquisition budgets, and freeze representative chronological datasets
  with an explicit availability model before comparing strategy performance.
  Jupiter backtesting retention was already confirmed by the user.

## Documentation fingerprints

These SHA-256 values identify the exact public documents retrieved for this
review; they are not market evidence or immutable provider-version promises.

| Document | Bytes | SHA-256 |
| --- | ---: | --- |
| Jupiter Price V3 YAML | 3,154 | `bc798556d98db9f5f5586cbd4deadd3c0839e167c2fffe93f8df9308acc7e029` |
| Birdeye OHLCV V3 Markdown with embedded OpenAPI | 19,088 | `f69fc4bd2224090b9e53ee2ccd3fae03d21fbed6e9e06fe2efaf8bdfa84cc691` |
| Solana getBlockTime Markdown | 2,801 | `850052bf0f8b89b4e585b2609ce63b105ba329f658cdfd344fcc01c4afa2b535` |

The official project-pinned Jupiter skill was used as a navigator after reading
`JUPITER-TOOLING.md`; current endpoint contracts took precedence. The documentation
MCP was not exposed as a callable tool in this session, so public HTTPS documents
were read directly. The older `docs.birdeye.so/reference/get-defi-v3-ohlcv` URL
returned 404; the current `data.birdeye.so` endpoint above was available.
