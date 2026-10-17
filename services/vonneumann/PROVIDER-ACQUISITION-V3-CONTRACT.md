# Original acquisition capsules and derivation — offline R3-02A slice

This slice implements useful deterministic acquisition evidence validation and
derivation in two **new** pure modules: `market/provider_acquisition_v3.py` and
`market/provider_derivation_v3.py`. It does not perform an acquisition or install
a recorder, archive, model, native package, reader, capability, lease, migration
or worker. All admission/authentication/archive/hosting/running/trading claims
remain false. Existing v2/v5 documents, sources, models and journals are unchanged.

The new research formats are `ga-provider-acquisition-capsule-research-v3`,
`ga-provider-public-request-research-v3`, `ga-provider-record-age-research-v3`,
`ga-provider-derived-observation-research-v3` and
`ga-provider-derived-history-research-v3`. They are deliberately distinct from
the proposal's future **native accepted** record/observation names. A research
capsule or derived DTO is not accepted native model state with a new label.
The capsule's parser-policy digest identifies the frozen descriptive policy;
it does not authenticate the Python code or its dependencies. Future operator
bindings must also pin the actual module/helper/runtime/package sources.

## Original record and external trust input

`IssuerBinding` is a separate explicit input supplied by an independently
trusted operator/reader. It binds canonical owner/run, durable market epoch,
process acquisition epoch, issuer binding, the permitted provider/endpoint IDs
and this parser-policy digest. The Python value and its IDs are **not** an
authentication proof, credential or authority token. Never derive a binding
from the same untrusted capsule and then claim provider/server authentication.
The future authenticated observer and accepted-head boundary are unimplemented.

`capture_capsule` takes the caller's original reserved record UUID, exact public
request bytes, exact response bytes/status, and actual explicitly supplied start
and receipt UTC/monotonic integer microseconds. It generates no UUID, clock or
random value. `decode_capsule` independently compares the separate binding,
canonical request, original byte count/hash/base64 and exact field/types.
Captured immutable bytes survive byte-for-byte, including whitespace and exact
numeric lexemes. Raw references are scoped UUIDs, never paths or private URLs.
The default raw reference is the explicit original record UUID, not a new ID.

The exact capsule keys are:

```text
format, owner_id, run_id, market_epoch, acquisition_epoch, record_id,
issuer_binding_id, provider_family, endpoint_binding_id, method,
canonical_public_request_wire, request_sha256, http_status, response_bytes,
response_sha256, raw_response_ref, response_base64,
request_started_wall_us, received_wall_us,
request_started_monotonic_us, received_monotonic_us,
safe_response_metadata, parser_policy_sha256
```

Capsules use bounded canonical UTF-8 JSON with string counters; duplicate and
unknown keys, raw numbers, noncanonical base64, changed scope/epoch/hash/bytes,
bad Unicode and unsupported requests are refused. The capsule cap is 6 MiB,
public request cap 4 KiB, raw Price cap 128 KiB, individual RPC cap 64 KiB and
raw history cap 4 MiB. Depth is 32, arrays at most 5,000 entries, individual
objects at most 1,024 keys and the decoded tree at most 200,000 values/keys.
Raw blobs are inline only for this pure experiment. This is **not** a proposal
to put them into the 262,144-byte active checkpoint or claim archive retention.

The only safe optional response metadata is `content_type=application/json`
and bounded canonical string integers for the three declared Jupiter quota headers.
Remaining is signed int64 (including zero and negative values); current is
unsigned through signed-bigint maximum, and reset is an unsigned absolute Unix
second bounded at 10,000,000,000. Negative zero, plus signs, leading zeros,
booleans, floating values and out-of-range values refuse. Jupiter's current
[rate-limit documentation](https://developers.jup.ag/docs/portal/rate-limits)
explicitly describes signed remaining and reset as the oldest slot's expiry
timestamp, not a duration or complete bucket reset.
Those headers are unverified diagnostic data, not billing/quota authority.
Auth headers, cookies, arbitrary header names, error messages and private RPC
URLs cannot enter the public request or metadata interfaces. Original response
bytes may contain provider diagnostics; callers must keep those private and
must not print raw bodies/capsules. DTO reprs omit raw data, and errors have one
fixed message without provider/caller text.

Non-200 failures, including empty failure bodies, can be retained as original
bounded diagnostics. They never become a price, network/time or history
observation. A timeout or new read attempt would need its own actual acquisition
identity; this slice supplies no retry, submission or original-ID lookup API.
Future record admission must preserve/reconcile the original ID/wire after an
uncertain write rather than silently substitute an ID.

## Secret-free requests and actual independent derivation

Price requests use the fixed Jupiter `/price/v3` endpoint and the one configured
SOL mint. The raw JSON is independently reparsed with duplicate rejection and
exact integer/Decimal lexemes. The parser requires a positive USD reference
price on the existing exact 18-place execution grid, a u64 block reference and
the configured mint's nine decimals. Known optional creation/liquidity/change
metadata receives type validation; creation time never replaces source time.
Unsupported/missing mint/fields refuse. A missing price is not zero. Current
official [Price reference](https://developers.jup.ag/docs/api-reference/price)
documents mint-keyed present-price data; this slice provides no historical Price
endpoint, executable quote, provider publication time or finality guarantee.

RPC public requests contain a canonical original JSON-RPC body with explicit
integer request ID, method and slot. The endpoint is the literal
`operator-bound-solana-rpc`; the independently supplied endpoint UUID resolves
the private connection elsewhere. Only `getGenesisHash` and `getBlockTime` are
allowed. Responses require the exact matching JSON-RPC version/ID, no error,
the configured mainnet genesis, and a non-null integer block time for the exact
Price block. Solana documents genesis as network identity and block time as
estimated block production, not provider publication or finality.
[Genesis](https://solana.com/docs/rpc/http/getgenesishash),
[block time](https://solana.com/docs/rpc/http/getblocktime).

The history request is a new fixed Birdeye Price OHLCV V3 request with `1m`,
`range`, USD, raw amounts, `padding=false` and **`outlier=false`**. All returned
rows, including excluded older/forming rows, are validated. Timestamps, mint,
currency, OHLC inequalities, nonnegative base-token/USD volume, exact decimal
grids, duplicate consistency and unscaled null/one multiplier rules are enforced.
Unknown fields, gaps, changed consumed overlap, scaled tokens or invalid
boundary rows refuse. Numerical lexemes survive exactly as canonical decimal
strings; integer-only volume sums ignore ambient Decimal precision/traps.
Birdeye's current [OHLCV documentation](https://data.birdeye.so/docs/data-api/price-ohlcv/get-defi-v3-ohlcv)
states that false filters outliers and empty buckets are absent without padding.
Filtering can therefore yield a refused incomplete window; no missing candle is
invented. Literal synthetic fixtures do not prove actual response-schema,
coverage, revision, outlier, subscription or retention behavior.

`derive_history` produces 915 complete minutes and 61 complete 15-minute bars
for bootstrap, or exactly one next bar after verifying every minute of the
previous consumed 15-minute overlap. End is the actual supplied UTC cutoff
after the unchanged five-second completion margin. Request start, receipt and
current clock must agree on that cutoff. The previous immutable history DTO
and a separately supplied expected prior digest are both required for an
increment. The expected hash must come from the future authenticated accepted
head, not from the untrusted request. This pure function grants no acceptance.
It returns original pin/provenance and all minutes/bars; it changes no EMA/model.
Against that available historical predecessor, a reused record UUID must retain
the exact capsule SHA, and a reused raw-reference UUID must retain its response
SHA. This applies to direct history derivation and packets supplied only with
previous history, independently of the optional previous-observation seam.
Identical old request bytes cannot qualify as the next bar because their range
has not advanced. This is a local known-predecessor check; the full authenticated
append-only history/identity ledger remains a separate native requirement.

`derive_observation` reparses one Price, one genesis and one block-time capsule
plus optional history. It emits exact mark/source/clock/range/raw-pin metadata.
Every packet record has a distinct original record/raw-reference identity.
All record receipt ages and min/max receipts are included. The resulting
manifest/hash is deterministic; it never creates a source sequence, trade,
decision, completed evaluation or accepted native head.

## Conservative epochs, cache and source-age rules

`ClockBound` is an explicit independently bounded UTC interval and process
monotonic reading. It reads no clock and cannot authenticate those samples.
UTC uncertainty is capped at two seconds. Receipt and successful acquisition
durations remain strictly below five seconds; estimated-source age is at most
30 seconds and the future tolerance at most two seconds. These are proposed
pure-policy checks, not final native/COMMIT observations. The actual future
native boundary must capture its genuine clock after independent processing
and recheck all records at admission/commit; a timestamp that ages into the
allowed window is judged against that actual captured observation.

Same-process age includes monotonic elapsed time and conservative UTC age.
For an unrelated acquisition epoch, monotonic origins are never subtracted.
Reuse requires independently bounded UTC ordering; unknown/reversed ordering
refuses. Prior age snapshots may only advance, with lower/upper UTC elapsed
bounds across epochs. Neither source nor receipt clocks are rebased on cache
hits, and old original capsules remain unchanged. Stale cache evidence requires
a fresh acquisition rather than a refreshed label.

Optional prior-observation DTO plus separate expected digest carries source-age
floors/ceilings to a fresh packet. Lower block/source references refuse, and a
repeated block cannot change its estimated time. Source advancement can subtract
only the actual estimated-time increment; a fresh HTTP receipt for the same old
source does not reset age. Cross-process carry uses bounded UTC, not the new
process's lower monotonic origin. The retained predecessor's observation ID
cannot be reused, and any reused record/raw-reference ID must retain its original
bytes/hash. This checks only that predecessor; a future authenticated append-only
identity/record ledger must enforce the complete historical set atomically.
No source-counter advancement is implied.

The first profile requires **fresh genesis and block-time acquisitions in every
active packet**. All newly used RPC and history records contribute to freshness;
there is no silent cached-genesis exemption. A later immutable network-anchor
cache policy must explicitly separate its trust/epoch lifetime from current
acquisition freshness and be measured/accepted independently.

Long or multi-bar backlog is refused. A fresh 61-bar warmup cannot be substituted
for exact continuation of an older EMA, especially after a >915-minute outage
with no retained overlap. Stop or an explicitly reviewed fresh run remains
possible through future control APIs. A causal catchup/indicator-reset operation,
gap/withheld-cohort event and process rollover require new model/native proofs;
this loader/deriver neither discards indicators nor fabricates missed trades.

## Acceptance and the remaining joins

The initial `7374539` slice passed 25 focused cases; its composed run with the
unchanged provider-evidence and exact-record suites passed all 77 cases, zero
skips, in 3.424 seconds under locked CPython 3.12.14. That receipt is historical
and predates the quota/predecessor correction below. It checked useful exact old/new price precision,
915-minute/61-bar and incremental history, original-byte round trips, all-record
receipt bounds, unrelated process clocks, immutable age/source carry, stale and
future data, uncertainty, no-overlap/backlog, HTTP errors, scaled/padded/gapped/
revised data, unknown/duplicate/type/number/Unicode/byte/depth/row limits and
resource-import denial. No provider request, credential read, DB, native install,
clock/RNG generation or hosted action occurs. Repeat the composed final-head
ordinary suite before integration/release; these tests are not CI/native/hosted
acceptance of a runtime. Example:

```sh
env -i PATH=/private/tmp/dashboard-locked-worker/bin:/usr/bin:/bin \
  PYTHONPATH=services/vonneumann PYTHON_DOTENV_DISABLED=1 \
  PYTHONDONTWRITEBYTECODE=1 /private/tmp/dashboard-locked-worker/bin/python \
  -m unittest tests.test_provider_acquisition_v3 -v
```

Independent read-only source/test review found no blocker within the declared
pure, unauthenticated DTO scope. Prior DTOs and expected hashes remain external
trusted caller inputs; this review does not establish a native accepted-head
oracle, authenticated archive continuity or actual acquisition transport.

### Quota/predecessor follow-up acceptance

Root review identified that unsigned remaining wrongly rejected a legitimate
429 diagnostic with a negative remaining header. Independent native review also
identified that a history-only increment could reuse its available predecessor's
record/raw-reference UUIDs with changed bytes. Both are repaired in this new
local slice, with six additional focused cases. The corrected 31 focused cases
plus the same 52 provider-evidence/exact-record cases pass **83 cases, zero
skips, in 3.295 seconds** on the final corrected policy source. Cases cover `-1`, signed minimum/maximum, empty 429
bodies, zero/absent headers, reset-second bounds, malformed signed/unsigned
values, unknown authority fields, unchanged USD denomination, null runtime/code
bindings and false profile authority; direct/packet history ID substitutions
refuse while ordinary positive increments retain exact overlap.

Parser policy format is now
`ga-provider-acquisition-parser-policy-research-v3-quota-v1`, with explicit
signed quota and known-predecessor identity clauses in its canonical digest.
Historical capsules from `7374539` retain their original policy hash
`396df7236cb58fed359714b77110075791709eb894a0833e5fb7eb05aef863b9`.
The current decoder refuses that unsupported earlier policy binding rather than
silently rewriting its capsules. Future archive/old-reader support must pin and
validate the appropriate original code/policy. This policy digest remains a
descriptive identity, not a runtime source digest, authentication token or
native acceptance. No existing model/profile version or original v2/v5 wire was
changed; no runtime/module pin is populated and no authority flag is enabled.

The following ordered work can be implemented with offline fixtures now:

1. Authenticate the actual scoped observation issuer and bind reviewed code,
   runtime, source/endpoint identity, actual capture clocks and original-ID
   recording. Prove real safe response schema/units without claiming authenticity
   from hashes. Independently accepted raw/clock/source pins remain required.
2. Build the fresh v3 model/config/source adapter in parallel after the interface
   freezes, preserving GA math/RNG and original synthetic-v2 journals. Prove
   interruption withholding, explicit process rollover and supported backlog
   behavior, then compose independent native semantics and atomic effects.
3. Implement owner-scoped immutable raw storage and original-ID lookup, archive
   closure, unavailable/corrupt/foreign archive refusal and code/version pins.
   Measure real raw/index/TOAST/WAL/Stop/clock/RPC/quota budgets. Inline pure blobs
   or this fixed policy digest cannot substitute for that acceptance.
4. Join v3 restore/projection/authenticated reader/control and old/new histories;
   rehearse the exact-project closed migration/rollback; then perform bounded
   closed/hosted multi-window/restart/held-position/fault acceptance.

Jupiter backtesting retention is already user-approved. Separate Birdeye
subscription/coverage/retention rights remain unknown; public general and
supplemental/account API terms must be resolved before real history collection
or retention. This experiment acquires no Birdeye data and draws no blanket
legal conclusion. No general additional user approval is needed for the offline
implementation work. Railway's approved $20/month ceiling remains in force;
actual paid/account-wide changes and all live signing/funding/swaps stay outside
this slice. The whole fifth-priority/native/continuous-paper gates remain open.
