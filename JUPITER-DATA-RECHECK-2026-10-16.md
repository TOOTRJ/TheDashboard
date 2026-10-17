# Jupiter data recheck — 2026-10-16

This bounded recheck supplements `JUPITER-TOOLING.md`, `services/vonneumann/JUPITER-DATA-RESEARCH.md`, the October 7 API review manifest, and the current paper-runtime plan. It changes no endpoint integration, data policy, account setting, or implementation.

## Finding and searched scope

No general historical SOL/token OHLCV, candle, or arbitrary past-price-range endpoint was found in the current official documentation searched. This is a scoped non-discovery, not proof that no private or unindexed Jupiter product exists. The search covered the [complete documentation index](https://developers.jup.ag/docs/llms.txt), its historical/OHLC/candle references, the three raw contracts below, Price/Tokens references, portal quota/plan pages, AI skills, the listed changelog, and targeted official-domain search. Indexed history operations concern orders, positions, trades, or invites; they do not establish a general token-candle service.

The [Price documentation](https://developers.jup.ag/docs/price) and actual Price V3 contract expose current prices for up to 50 mint IDs. `createdAt` describes token creation, and `blockId` identifies the block used to compute the price; neither is a historical query selector. Tokens V2 exposes search, tags, category/interval lists, recent tokens, and rolling 5-minute/1-hour/6-hour/24-hour statistics. Those aggregates are not historical candle retrieval. The [AI skills page](https://developers.jup.ag/docs/ai/skills) still broadly mentions historical pricing, but the searched Price contract supplies no implementable history operation. This documentation mismatch was already identified previously.

## Raw documentation evidence

All four documentation GETs returned HTTP 200. The current index was 100,566 bytes, SHA-256 `825096d5b5eb36bc08ead657cc481f61d7af29b0b17b2d75cf1df82cc3d1464e`. Raw YAML was read and hashed directly; this was not solely an HTML-page review.

| Official contract | Current bytes | Current SHA-256 | October 7 comparison |
| --- | ---: | --- | --- |
| [Price V3](https://developers.jup.ag/docs/openapi-spec/price/v3/price.yaml) | 3,154 | `bc798556d98db9f5f5586cbd4deadd3c0839e167c2fffe93f8df9308acc7e029` | Same hash and length |
| [Tokens V2](https://developers.jup.ag/docs/openapi-spec/tokens/v2/tokens.yaml) | 15,639 | `a1ba94ded9c4cc2a4afe1d20c675bf09e50e4e388f2dffd1042f1ef348837535` | Same hash and length |
| [Swap V2](https://developers.jup.ag/docs/openapi-spec/swap/v2/swap.yaml) | 31,414 | `6fbde9bc19f82a1fba724181103d759fbe35f58f4aae865b4d943f01c1e26e6b` | Changed |

The October 7 Swap YAML was 31,368 bytes, SHA-256 `76daa0a94d51cb8ca2488b2cfae22f3ba7dab05444615c7169ce7893cb0ddd67`, as recorded in `services/vonneumann/jupiter-api-review-20261007.json`. Its old raw bytes were not retained, so these hashes do not identify the semantic change. Current paths remain `/order`, `/build`, `/execute`, and `/program-id-to-label`. Do not infer a new historical feature or claim an exact contract diff. Re-review the actual Swap contract before future execution changes. Managed execution, build, transaction-v1 support, and AMM test tooling were already discussed in the prior report; no newly verified historical-data tool emerged here.

## Authentication and quota limits

The Price contract declares `x-api-key` authentication. [Portal rate-limit documentation](https://developers.jup.ag/docs/portal/rate-limits) separately describes limited keyless access and organization-wide allowances: examples include keyless 0.5 RPS, Free 60 requests per 60 seconds, and Developer 600 per 60 seconds. These are public examples, not observed TheOrder entitlements. Price, Tokens, and Swap share the main organization allowance; generating another key does not create another organization quota. `/swap/v2/execute` has a separate documented bucket. Endpoint credit weights and sliding-window behavior must also be budgeted. [Plans](https://developers.jup.ag/docs/portal/plans) describe allowance differences, not improved price freshness. Existing observed-header questions remain unresolved; no account or quota probe was performed.

## Implementation consequence and remaining research

Keep the selected Jupiter-only prospective close profile: 915 genuinely observed contiguous minutes produce 61 complete 15-minute close bars for the fixed two-EMA research model. That model does not require high/low/volume. Original Price/genesis/block-time evidence, committed-readback availability, bucket boundaries, gaps, and restart/epoch continuity remain necessary. A historical download obtained today cannot establish that an observation was available at an earlier decision. Neither historical bars nor recorded closes reconstruct amount-specific executable quotes or fills.

Birdeye remains optional for this prospective profile. Evaluate its rights, coverage, revisions, and entitlement only if a retrospective dataset is selected. The user's Jupiter backtesting-retention permission remains accepted; it does not require reconfirmation.

Prioritize deeper measurement of source age, repeated blocks, omissions/gaps, effective shared quota, causal availability and restart continuity; prospective-versus-retrospective revisions and held-out baseline comparisons; and separate execution fees, latency, rejection, expiry, and fill-cost calibration. Native source/model joins and continuous hosted operation remain separate gates.

This research used public documentation only: no product API or account/key requests, installation, tool configuration, prototype, native execution, or test. No task-owned raw-schema files or request logs were retained on the filesystem; selected documentation outputs remain in the conversation record. This note preserves hashes and findings, not an archived raw-body corpus or a reproducible semantic diff.
