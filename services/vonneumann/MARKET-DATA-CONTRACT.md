# Immutable offline market datasets

DATA-01B is a software-testing foundation. A validated content hash identifies
input bytes and their declared meaning; it does not establish provider
authenticity, execution quality, archival permission, or profitable trading.

## Local generation and validation

Use the worker's installed Python environment from the repository root with
`PYTHONPATH=services/vonneumann`. The dataset CLI imports no application
configuration, reads no credentials, and makes no network requests. Generate
synthetic fixtures into a new local directory outside the source tree. Existing
directories are refused rather than overwritten. See `python -m
vonneumann.market.dataset_cli --help` for the supported commands and bounds.

```sh
PYTHONPATH=services/vonneumann python -m vonneumann.market.dataset_cli generate-synthetic \
  --output /private/tmp/dashboard-fixture-32 --frames 501 \
  --assets SOL/USDC JUP/USDC --seed 32
PYTHONPATH=services/vonneumann python -m vonneumann.market.dataset_cli validate \
  /private/tmp/dashboard-fixture-32
```

Use an existing physical parent directory: the loader/writer refuses symlinks
in every path component, including macOS `/tmp` (use `/private/tmp`). The CLI
sorts the requested asset set before generation so argument order does not
change fixture identity. Seeds are canonical unsigned 64-bit decimal strings.
The current limits are 10,000 frames, eight assets, 32 MiB of frame bytes,
256 KiB per frame line and 64 KiB for the manifest. This bounded in-memory
format is intended for fixtures; larger research archives need a separately
reviewed storage/streaming design. Both commands print a safe metadata summary
with the dataset ID and return nonzero on failure.

Each dataset contains exactly the contract files `manifest.json` and
`frames.jsonl`. JSON is canonical UTF-8 with sorted keys, compact separators,
finite numbers, and a final newline. A SHA-256 digest covers the exact frame
bytes. A second SHA-256 digest covers the canonical manifest, including the
frame digest. Record the resulting dataset ID in the experiment ledger; there
is no self-referential ID inside the manifest. Copying a directory preserves its
identity; changing content or metadata produces a different identity. The
writer does not overwrite an existing bundle. This is application-level
immutability, not an operating-system write lock or a signed certificate.

The loader bounds file sizes, frame count, line sizes, and the asset universe;
rejects duplicate/unknown keys, noncanonical JSON, invalid numbers, nonregular
files and symlinks; verifies both schema and payload integrity; and returns
deeply immutable records. Consumers must load through this validation boundary.
Do not use pickle, archive extraction, URLs, or unvalidated hand-built objects.

## Meaning and chronology

Metadata records the ordered asset universe and mints, network, source kind,
quote/candle providers, USD price units, volume units and meaning, source-time
and availability semantics, valuation policy, rights declaration, evaluation
bounds, and the synthetic generator specification where applicable.

Each frame has a strictly increasing observation time and exactly one quote for
every declared asset in declared order. Quotes carry source and receipt time;
provider observations also carry a source slot. Source time cannot exceed
receipt time, receipt cannot exceed frame observation time, and per-asset
source evidence cannot regress. Synthetic volume is explicitly modeled;
Jupiter's unavailable quote volume is an identified zero placeholder, not a
measurement of zero trades. Legacy asset labels such as `SOL/USDC` are engine
identifiers; they do not override the manifest's USD price units.

Completed one-minute candles retain OHLC, volume, source/unit labels and an
availability time. Candle end must be at or before availability, which must be
at or before its containing frame. First arrivals must be contiguous. Exact
duplicates retain their original availability; conflicting revisions, gaps,
invalid ranges, or unit changes fail validation. A later historical download
must not label its candles as contemporaneously available at their closes.
This strict normalized format does not preserve arbitrary raw provider
responses or silently repair bad observations.

Empty or delayed candle deliveries and partial leading/trailing history are
permitted for availability tests. Validation rejects interior gaps among
delivered minutes; it does not certify complete candle coverage of the quote
timeline. The CLI reports each asset's unique candle count and observed range
so missing coverage remains visible. A declared experiment warmup additionally
requires every minute in its required range to have been delivered by the
evaluation start. A later frame with a backdated availability label cannot
satisfy that warmup requirement.

## Synthetic playback

`ReplayFeed(path)` starts a new independent cursor after loading the complete
bundle. Every nonempty `get_ticks(assets)` advances one whole frame, regardless
of the requested subset/order. An empty request does not advance; an invalid
asset fails before mutation. `get_tick(asset)` also advances a whole frame, so
use a batch call for simultaneous assets. End-of-data raises
`MarketFeedError("dataset_exhausted")` with no fallback quote or clock advance.

`get_candles(assets)` releases each canonical minute once per asset, only after
its containing quote frame has been delivered. It returns any unseen backlog
for those assets, never advances the clock, and never exposes later frames,
including when `warmup=True`. Repeated reads may return an empty list. A shared
controller candle history supplies repeat access for probes and descendants.
The modeled clock begins at the original simulation start time. Mutable tick
objects and copied metadata cannot mutate the validated dataset.

The existing controller accepts this feed only in simulation mode and records
its dataset ID, frame hash, count, source/unit policy and playback version in
the persisted `search_spec` JSON. The HTTP API does not accept dataset paths or
introduce a new replay endpoint. Instantiate the feed locally in offline tools.

Playback currently requires zero declared experiment warmup and an evaluation
window spanning the entire synthetic timeline. It refuses other windows so it
cannot silently ignore a requested split. Normal probe indicator warmup still
occurs in the engine. A complete experiment runner, held-out splits, durable
result ledger and resumable optimizer/account state remain separate work.

Provider observations can be checked against the normalized archive schema,
but `ReplayFeed` explicitly refuses them. Historical playback needs a recorded
wall/monotonic clock model, quote-age enforcement at every consumer, truthful
candle publication evidence or declared modeling assumptions, and realistic
fills. Selecting simulation mode must never bypass those requirements. No
provider collector, hosted worker, database migration, or wallet action is
part of this feature.

## Research gates

The user confirmed Jupiter backtesting retention on 2026-09-30; accept that
permission. The next acquisition step is selected historical windows with frozen
research snapshots, not continuous archiving. See [provider research](JUPITER-DATA-RESEARCH.md).
Resolve separate Birdeye entitlements/retention, point-in-time coverage and
survivorship, exact request/scaling semantics,
publication delays and revisions, raw response/query/parser provenance, and
USD versus USDC accounting. A rights flag in a manifest is a declaration, not
verification of a contract. Before comparing evolutionary candidates, add
cost-aware executable fills, a frozen representative dataset and a versioned
result/experiment manifest. See RES-01 through RES-03, FILL-01 and DB-03 in the
root TODO, and configuration report section 26.
