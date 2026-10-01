# Jupiter and historical research data

Research and decision date: **2026-09-30**. This document supports DATA-01/DATA-02/DATA-03, FILL-01B, RES-02/RES-03 and the baseline experiment in [TODO.md](../../TODO.md).

**Decision: obtain small historical windows on demand and preserve immutable research snapshots. Do not build a 24/7 archive at this stage.** Fetching history and retaining an experiment's exact input are complementary: the provider supplies history; the snapshot makes repeated candidate evaluations reproducible without repeated requests. Expand collection only when a defined experiment needs evidence that cannot be recovered later.

The user has confirmed that Jupiter permits this project's backtesting retention. Accept that confirmation; Jupiter retention permission is not an outstanding blocker. Birdeye's account entitlements, applicable retention terms and any redistribution rights remain separate unknowns. Public endpoint availability is not proof of this account's purchased access or archival rights.

This research used public documentation only. It did not query account APIs, acquire provider datasets, access credentials, place orders or change provider settings.

**What the APIs provide**

| API | Appropriate role | Historical limitation |
| --- | --- | --- |
| Jupiter Price V3 | Current USD reference marks, with `blockId`, token decimals and 24-hour percentage change; up to 50 mint IDs per request. | No historical time/range request is documented in the reviewed Price V3 interface. Unreliable/inactive tokens can be omitted. A percentage change is not a price series. |
| Jupiter Tokens V2 | Mint identity, decimals, discovery, verification, liquidity and trading statistics. | Current discovery/risk metadata must not be assumed to describe a past universe or historical risk state. |
| Jupiter Swap V2 | Amount-specific current quotes and optional execution integration. | The reviewed quote interface has no historical date/slot selector. It does not reconstruct a past hypothetical order. |
| Birdeye OHLCV V3 | Historical token candles; the separate pair endpoint covers individual pools. | Up to 5,000 records per request. Missing trading intervals are omitted unless padding is requested. Second-level history has shorter retention. |
| Birdeye historical price | USD line series for a token/pair, or a single Solana Unix-time checkpoint. | Line/checkpoint prices do not supply OHLCV volume or an executable order price. |
| Birdeye historical trades | Observed token/pair/wallet transactions, including time-bounded endpoints. | Other traders' completed trades do not establish this bot's available route, delay or counterfactual fill. |

Sources: [Jupiter Price](https://developers.jup.ag/docs/price), [Tokens](https://developers.jup.ag/docs/tokens), [Swap order reference](https://developers.jup.ag/docs/api-reference/swap/order), [Birdeye OHLCV V3](https://data.birdeye.so/docs/data-api/price-ohlcv/get-defi-v3-ohlcv), [historical price series](https://data.birdeye.so/docs/data-api/price-ohlcv/get-defi-history-price), [Unix-time price](https://data.birdeye.so/docs/data-api/price-ohlcv/get-defi-historical-price-unix), [Birdeye API index](https://data.birdeye.so/docs/llms.txt).

The Jupiter [skills overview](https://developers.jup.ag/docs/ai/skills) broadly describes historical pricing, but the reviewed [documentation index](https://developers.jup.ag/docs/llms.txt) and Price V3 contract do not identify a general historical price/OHLCV endpoint. Treat this as a discovery question: require an actual supported endpoint/schema and its limits before designing around it. Account-specific Trigger/DCA order history is a different capability.

**Keep three kinds of evidence distinct**

1. **Historical bars downloaded today:** provider-reconstructed OHLCV for past intervals. Store retrieval time, parameters, coverage and revision identity. The timestamp of a bar is not evidence of when the live bot could first receive it.
2. **Observations recorded while a session runs:** the exact responses, source evidence, receipt times, failures and availability seen by the application. These support live/paper incident replay and latency analysis.
3. **A past hypothetical fill:** an estimate for an order the bot did not place. Candles and observed trades cannot uniquely recover its route, market impact, inclusion, rejection or realized slippage. Record execution assumptions separately and perform sensitivity analysis.

An immutable snapshot freezes our input, not the provider's original publication history. Historical playback must explicitly model availability and subsequent execution observations; never fabricate old Jupiter quotes or receipt times from candle closes. The present [dataset contract](MARKET-DATA-CONTRACT.md) supports synthetic replay and provider-shaped archive validation; it does not yet implement provider historical playback. [FILL-01A](EXECUTION-CONTRACT.md) supplies uncalibrated USD reference percentage costs, not verified Solana fills or USDC settlement.

**Data needed for the current small search**

The existing two-gene replay fixtures vary `rsi_oversold` and `volume_threshold` within the current RSI/EMA/volume decision engine. They still require valid completed closes, real interval volume, enough RSI/EMA warmup, and the preceding 20 completed volume intervals. A Jupiter spot-price series cannot replace that volume history. Price-only data also cannot reconstruct intrabar stop ordering.

This differs from planned **BASE-01**: optimize only `ema_fast` and `ema_slow`, explicitly disable RSI and volume features, and fix the asset, timeframe, risk controls and evaluation windows. Choosing two evolvable genes does not itself disable other features or freeze asset selection. Confirm the experiment profile before acquisition; retain OHLCV as a reusable input even if the first baseline only consumes closes.

Recommended first corpus: one disclosed liquid asset, then a second robustness asset, with a small set of chronological windows spanning different conditions. Use minute bars and aggregate supported longer intervals consistently. Separate warmup, training, validation and untouched test periods. A present-day handpicked universe is acceptable for a narrow experiment if disclosed; it does not establish performance across historical launches or failed tokens.

**Retention, request limits and entitlements**

- Birdeye documents **1-second candles for two weeks** and **15-/30-second candles for three months**. Minute-and-higher coverage must be checked per asset/window; the FAQ's SOL history since 2021-12-09 is not a universal completeness guarantee. [Retention](https://birdeye.so/data-api/blog/detail/introducing-sub-minute-intervals-in-birdeye-data-services-ohlcv-v3-apis), [SOL coverage](https://data.birdeye.so/docs/resources/faqs).
- The current accessibility table marks OHLCV V3, historical series and Unix-time prices available on **Standard**; token/pair seek-by-time requires **Lite/Starter or higher**, and WebSockets **Premium or higher**. This differs from older blog tier descriptions. Verify the user's actual entitlement before spending or assuming an upgrade is required. [Accessibility matrix](https://data.birdeye.so/docs/guides/data-accessibility-by-packages).
- Standard's published allowance is **30,000 CU/month, 1 request/second**. OHLCV V3 lists dynamic tiers up to **100 CU for 5,000 records**; a two-asset, 30-day minute dataset has at most 86,400 regular buckets, approximately 18 maximum-size requests and 1,800 CU before warmup/retries. This is illustrative, not a billed usage prediction. [Pricing](https://data.birdeye.so/docs/guides/payment/pricing), [OHLCV costs](https://data.birdeye.so/docs/data-api/price-ohlcv/get-defi-v3-ohlcv).
- Jupiter's published main limits are Free 1 RPS, Developer 10, Launch 50 and Pro 150, shared per organization. Birdeye limits are shared per account. Separate application keys do not create separate quota capacity; budget alongside the user's other project. [Jupiter limits](https://developers.jup.ag/docs/portal/rate-limits), [Birdeye limits](https://data.birdeye.so/docs/guides/api-access/rate-limiting).

**Provider ambiguities to resolve**

- **Outliers:** Birdeye's OHLCV usage note says `outlier=false` produces raw candles without filtering; its parameter text says `outlier=true` allows outliers. Confirm the actual behavior with provider clarification and controlled fixtures. Persist the selected flag and interpretation instead of silently depending on a default. [Conflicting descriptions](https://data.birdeye.so/docs/data-api/price-ohlcv/get-defi-v3-ohlcv).
- **Checkpoint time:** historical Unix pricing is described as exact in prose but “resolved near” the timestamp in the response schema. Inspect `updateUnixTime`, require a documented causal policy and reject future-relative checkpoints for historical decisions. [Checkpoint schema](https://data.birdeye.so/docs/data-api/price-ohlcv/get-defi-historical-price-unix).
- **Publication and revision:** establish completed-bar availability, backfills, revision behavior, pagination boundaries and earliest coverage before interpreting history as live-available evidence. Pin USD/base-token units and Token-2022 scaling semantics. The current adapter already requests `chart_type=price`, `currency=usd`, `ui_amount_mode=raw`, `padding=false`; those settings are not unresolved omissions.

**Jupiter integration architecture**

Keep Price V3 marks, Tokens V2 metadata and Swap V2 executable quotes behind separate interfaces. Metadata verification/organic score is a screening input, not a safety guarantee, and rolling token statistics do not replace historical candle volume.

For later amount-specific quote calibration, evaluate the managed **`/swap/v2/order` + `/execute`** path first; `/order` without `taker` supplies quote-only information. The alternative **`/build`** path returns raw Metis instructions for integrations needing transaction customization, with self-managed submission or Jupiter landing. The managed path competes multiple routers; `/build` has different routing and fee responsibilities. Choose on measured total execution quality, not headline request latency. No signing, broadcast or live trading is authorized by this research decision. [Swap architecture](https://developers.jup.ag/docs/swap), [quote-only behavior](https://developers.jup.ag/docs/api-reference/swap/order).

**Agent documentation tools**

Use Jupiter's [AI entry point](https://developers.jup.ag/docs/ai), [documentation index](https://developers.jup.ag/docs/llms.txt), official **`integrating-jupiter`** [skill](https://developers.jup.ag/docs/ai/skills) and read-only [Documentation MCP](https://developers.jup.ag/docs/ai/mcp) at `https://developers.jup.ag/docs/mcp` for schema checks. These improve integration research; they do not add historical endpoints. The Trading MCP is a separate operations surface. Keep any tool installation/configuration scoped to this dashboard task and preserve the other agent's settings. Installation verification is a separate setup action, not a claim established by this document.

**Research and implementation TODO, in priority order**

1. **P0 — Lock the baseline and data contract (BASE-01, RES-03).** Declare the actual features/genes, fixed universe, windows, units, warmup and allowable execution assumptions before acquiring data.
2. **P0 — Resolve Birdeye access and semantic questions (DATA-02, RES-03).** Confirm applicable plan/retention terms, outlier semantics, interval availability/revisions, causal checkpoint policy and finite request budget. Jupiter's user-confirmed retention permission remains accepted.
3. **P1 — Add bounded historical acquisition and replay (DATA-01/DATA-02).** Fetch only approved windows; validate/de-duplicate pages; preserve raw responses plus a normalized immutable manifest, hashes, retrieval time, source parameters, gaps and coverage. Version corrected imports separately. Implement an explicit historical availability/execution model and offline regression fixtures.
4. **P1 — Establish a reproducible comparison (BASE-02/BASE-03, RES-01).** Bind dataset, code, parameter policy, search seed and fill policy to every result. Compare fixed controls, a small exhaustive grid and evolution on identical data with held-out chronological evaluation and cost sensitivity. More generations do not create independent market evidence.
5. **P1 — Confirm Jupiter contracts (DATA-03).** Use the official skill/MCP and OpenAPI schema to resolve historical-pricing discovery, current quote/fee fields, rate limits and failure behavior. Mock contract tests precede provider changes.
6. **P2 — Calibrate execution with bounded paper-session recording (FILL-01B, RES-02).** Capture source/receipt times, amount-specific quotes, route/fee fields, failures and actual session observations. Study delay, impact, rejected orders, fixed network fees and USD/USDC conversion before economic claims.
7. **P3 — Reassess continuous collection (HOST-04).** Add a 24/7 collector only for justified expiring subminute history, launch-universe discovery or sustained quote/latency research. Require shared-quota accounting, storage/retention cost estimates and durable watermarks first.
