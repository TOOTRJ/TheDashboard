# Jupiter prospective source v3 — offline R3-01 contract and selection

This new source is `jupiter-price-v3-prospective-minute-sampled-close-v1`.
`market/prospective_source_v3.py` implements bounded deterministic research marks,
frozen inventory comparison, minute selection and close-only history derivation.
It makes no request, reads no environment, clock or database, allocates no UUID,
and changes no synthetic-v2 or provider-v5 format, model, SQL, reader or service.
All native, provider-attestation, current-freshness and running authority remains
false. The separate acquisition slice is a dependency; its Birdeye history
derivation is not used or relabeled for this Jupiter-only source.

The existing Jupiter documentation and skill review is recorded in
[JUPITER-TOOLING.md](../../JUPITER-TOOLING.md),
[PAPER-RUNTIME-V3-PLAN.md](PAPER-RUNTIME-V3-PLAN.md) and
[the acquisition contract](PROVIDER-ACQUISITION-V3-CONTRACT.md). This offline
implementation makes no new current endpoint, quota, provider entitlement or
transport-conformance claim. Recheck current Price V3/OpenAPI and Solana RPC
contracts when implementing the actual transport.

## Fixed source and strategy choices

Use one fixed wrapped-SOL mint, `SOL/USD`, Jupiter Price V3 reference prices and
mainnet genesis plus `getBlockTime` for the exact returned Price block. Price is
an exact positive canonical 18-place-grid string. The block time remains an
estimated production time, not Jupiter publication, finality or an executable
quote. The prospective source has no open, high, low or volume fields. It must
not be labeled OHLCV, pool trades, actual market close or historical executable
prices. USD reference accounting does not establish USD/USDC equivalence.

Retain the existing two EMA genes: fast 3…12, slow 15…60, eight genomes,
15-minute close-only bars and common one-hour cohort windows. No new signal,
mutation, selection, fitness or economic rule is implemented by this source.
The future v3 model must consume this separate source through a sealed versioned
interface; neither a source-label replacement nor a dictionary cast converts
the old synthetic or v5 model into it.

Bootstrap requires 915 contiguous observed UTC minutes, producing 61 complete
15-minute close-only bars. Beginning partway through a bar discards that forming
prefix. The earliest complete warmup is therefore 15h15m after the first full
bar begins, plus the five-second finalization margin; starting at an arbitrary
instant can require up to another 15 minutes. This is prospective collection,
with no backfill API or retrospective trades. A missing eligible minute refuses
the window; padding, forward-fill, interpolation and zero fallback are absent.

## Original records, origin trust and clocks

The acquisition dependency preserves exact original secret-free public request
bytes and bounded raw response bytes, canonical original record/raw UUIDs,
owner/run/market and acquisition epochs, endpoint and issuer binding IDs,
literal status, integer UTC/monotonic microseconds, byte counts and hashes.
Every active source packet requires fresh original Price, genesis and block-time
records. It independently parses the requested mint, mainnet genesis, exact RPC
request IDs, method/slot, non-null source second and exact Decimal lexemes.
This new slice accepts only the derived three-record Price/RPC observation,
without a Birdeye history attachment.

`RecordReference` is a **separate independently supplied trust input** binding
the original derived observation ID/hash, scoped native record admission ID,
unique increasing ingest sequence, recorder principal binding, reviewed recorder
package digest, native original receipt digest, `accepted_at_us` and
`available_at_upper_us`. Its Python constructor checks canonical types and
internal consistency only. It does not authenticate those values, call a server,
verify a role, establish transport TLS, check a complete ID ledger or grant
admission. Never construct it from the same untrusted observation and then call
that independent authentication.

The actual recording boundary must trust an explicitly scoped private observer
principal and pinned recorder/runtime/transport code. Pin HTTPS origins and the
private RPC endpoint binding, validate server certificates and hostnames, exclude
environment proxy/CA fallback, refuse redirects, keep credentials private and
retain original bounded bodies. Authenticate the native recorder principal
through actual server session identity/issuance and owner/run/package checks.
Independently reparse raw bytes and preserve the complete original record/raw/
observation identity ledger atomically. A body hash or recorder signature can
prove retained consistency or identify a recorder; it is not an independent
provider attestation or historical publication proof. No new credential, shared
configuration, role or capability is created by this work.

`accepted_at_us` identifies the genuine native ingestion observation separately
from worker receipt clocks. A SQL final guard can occur before final visible
COMMIT. Therefore `available_at_upper_us` additionally binds a clock-bounded,
authenticated **original committed readback** actually observed by the operator.
A returned provisional success or unknown/lost acknowledgement is insufficient.
Both clocks remain immutable. Reconciliation after a minute has ended cannot
retroactively claim that the record was available within that minute.

All three original receipt ages remain strictly under five seconds through that
original acceptance/readback; estimated source age is at most 30 seconds at
native acceptance, with the existing two-second future tolerance. All clocks
and counters are exact integer microseconds or canonical integer strings; no
binary floating-point conversion or future caller timestamp is introduced.
The derived observation carries source-age floors/ceilings, while this slice
conservatively accounts for elapsed UTC through acceptance/readback. The native
implementation must observe its actual clock after parsing/locks and preserve
the reviewed COMMIT guard guarantee limits. It must not trust this pure function
as a replacement for direct native source/lease checks.

`market_epoch` is durable; `acquisition_epoch` identifies one process/network
context. Preserve every original receipt epoch. Never subtract monotonic clocks
from unrelated processes or rebase old evidence onto a new receipt. The pure
sampled history can retain independently bound observations from several process
epochs, but it does not prove native rollover authorization, known epoch order,
network anchor lifetime or uninterrupted evaluation coverage. Actual process
restart requires original-command reconciliation, explicit native epoch rollover
and coverage-gap handling before new model actions. Loading history creates no
lease, activation, automatic pending-command retry or completed assessment.

## Deterministic minute selection and immutable finalization

For each UTC minute `[start, end)`, an eligible original record must have genuine
native `accepted_at_us` in that minute and an authenticated original committed
readback upper availability bound greater than minute start and at or before
minute end. Price receipt alone does not assign the minute. An original Price
receipt before end with native acceptance/readback after end cannot fill it.
Readbacks exactly at end are permitted; the resulting close offset is zero.

Within the independently frozen complete inventory, choose the maximum native
acceptance microsecond, then the unique native ingest sequence. Input order,
readback arrival order and arbitrary UUID lexical order do not choose the winner.
Duplicate sequence, observation or admission identities refuse. A reused original
record/raw UUID must keep the exact capsule/body hash. Ingest order cannot regress
native acceptance time, block or estimated source time; a repeated block must
keep the exact source time and price. Repeated HTTP acquisition does not reset
the source-age floors established in the acquisition/native boundary.

`SealReference` independently pins owner/run/market, source-policy and recorder
package digests, original seal UUID, complete record-inventory digest, through
ingest sequence, aligned start/end and a seal time at least end+5s. The pure
function compares this explicit inventory and never authenticates its completeness
or permanently locks a native range. The real native record store must freeze
the original inventory/head once, forbid reopening or later retroactive insertion,
and provide authenticated original seal readback. Later data remains separate
diagnostic evidence, never a revision to a consumed minute. The proposed five-
second margin is closed until actual collection/ingest/readback tails are measured.

Every 15-minute bar retains all 15 selected minute-anchor pins and their canonical
manifest hash. Its close is the final minute's selected original mark. Explicit
`close_offset_us` is the interval from committed-readback upper availability to
bar end, constrained to `[0,60s)`. Separately retain the mark's estimated source
age at original native acceptance. Sample offset and source age describe distinct
facts; neither establishes the actual executable price at the bar end.

An increment requires exactly the previous consumed 15-minute overlap plus one
new 15-minute bar, a separately supplied expected previous-history digest, a new
seal UUID and byte-identical original overlap anchors/bar. It retains 915 minutes
and 61 bars, appending only one bar. Changed overlap, gaps, omitted overlap or
multiple-bar backlog refuses. Check every available identity in the retained
predecessor, including IDs outside the overlap; the full historical native ledger
is still required for identities older than this bounded history.

The history's original freshness-at-acceptance evidence remains historical.
Fifteen-hour-old warmup records are not relabeled as current fresh observations.
Each new protective or decision action independently needs a genuinely fresh
Price/genesis/block-time packet, current scoped authority and actual native
source/lease/epoch checks. History retrieval cannot produce a new source sequence,
valuation action, retrospective trade, evaluation or authority.

The model seam is `derive_close_series(SampledHistory,
expected_history_sha256=...) -> SampledCloseSeries`. The expected history digest
must come from the future independently authenticated history reader. This
bounded immutable typed research DTO carries exactly 61 close/interval records,
source-policy and recorder-package pins, the complete original history digest,
all per-bar minute-anchor pins and explicit final-minute mark, observation,
native original-readback and raw-record pins. Recompute bar manifests from the
915 exact minute anchors before projecting. It grants no model ownership,
native admission, source freshness or runtime authority. Full history and raw/
native records remain required dependency lookups; the projection is not a
replacement for their retention or authentication.

For protective/decision input, `validate_mark(SourceMark,
expected_mark_sha256=...)` revalidates the immutable original mark against a
separate expected digest. `validate_current_mark(SourceMark, ClockBound,
expected_mark_sha256=...)` also checks genuine supplied current bounded UTC and
same-process monotonic time, all three original receipt ages, carried source
age/future bounds and the new explicitly pinned
`integer-us-causal-after-original-readback-and-latest-receipt-v1` action policy.
The current UTC lower bound must be at or after the original committed-readback
availability upper bound; overlapping uncertainty cannot prove a known-available
causal action. It must also be at or after every original trio receipt microsecond.
An action genuinely known after both boundaries within the same fractional
second is permitted; this new v3 policy introduces no artificial ceil-to-next-
second wait. Integer-second flooring may remain in reviewed cohort/calendar
math, never as source/action authority. Original v2 policy remains unchanged.
Earlier research acquisition bytes retain their original policy meaning through
their pinned decoder/package; the new reader explicitly refuses unsupported old
policy hashes. [Current nullable-metadata policy change](PROVIDER-METADATA-POLICY-2026-10-13.md).
It reads no clock and returns the original research mark, never action permission.
The model must additionally compare the separately accepted owner/run/market/
acquisition/package binding; native current-head/principal/epoch/lease/package
and post-processing clock checks remain independently required. A stale or
foreign-process historical mark cannot become current by loading or relabeling.

## Bounds and next implementation interfaces

The pure slice caps each mark at 16 KiB, supplied records at 4,000, frozen manifest
at 1 MiB and complete research history at 4 MiB. It requires tuple input, bounded
duplicate-free canonical JSON, explicit UUIDs and exact canonical counters.
These are offline experiment bounds; they are not a measured operating cadence,
storage allowance or the compact active checkpoint size. Raw bytes stay outside
the source manifest/checkpoint and remain mandatory retained dependency pins.
All supplied records receive validation, including excluded late records.

Build the next boundaries in this order:

1. **R3-02A recorder and authenticated original storage:** one owned no-retry
   bounded Price+RPC transport; reserve original acquisition IDs before I/O;
   retain original HTTP failures as diagnostics; private immutable raw store;
   native original record submit/getter and actual clock/issuer/package checks.
   An uncertain write retains the exact original ID/wire until reconciliation.
2. **R3-02B fresh model in parallel:** typed v3 source/config/state using these
   close-only bars and the unchanged reviewed GA/economic primitives. Compare
   exact full/compact next wires on immutable common corpora. No v2/v5 cast.
3. **R3-03 native composition:** complete current and retired ID/epoch ledger,
   independent raw derivation, frozen-range original seal/getter, scoped observer
   issuance, operator fencing, exact pins and current action/commit checks.
4. **R3-04/05/06A in parallel after native schema freezes:** restoration and
   explicit restart gaps; dependency-safe retention/physical budgets; offline
   owner-authenticated projection/API/reader integration.
5. **Closed exact-target migration and hosted read/control proof**, followed by
   bounded finite paper operation only after package/quota/resource acceptance.

Offline transport tests must prove TLS/hostname policy, no proxy/CA environment
fallback, no redirect/retry, bounded bytes/headers/JSON/operation/cleanup, whole-
packet deadlines, actual receipt capture before parsing and all records' clock
contribution. Native fixtures must prove original lookup after lost readback,
scope/issuer/package mismatch, raw/normalized forgeries, direct clock/future/age
edges, explicit epoch rollover, frozen inventory immutability, late-ACK gap and
Stop without new market data. Hosted requests/migrations are separate gated work.

Measure polling cadence, repeated-block frequency, Price→RPC→native/readback tails,
late-anchor/gap fraction, conservative UTC uncertainty, required principal
rotation across 15h15m warmup, CPU/RSS/raw/table/index/TOAST/WAL growth, request
quota/credits and reserved Stop/reconciliation capacity before activation.
Private-principal lifetime and recorder package upgrades need an explicit native
compatibility/rotation policy, not implicit relabeling of already sealed records.
Keep the approved $20/month pilot design ceiling without account-wide billing
changes. No live funding, signing, swaps or trading is implemented or authorized.

## Bounded verification

`tests/test_prospective_source_v3.py` uses literal original Price/RPC bodies and
independent explicit reference fixtures under the network denial guard. It checks
915-minute/61-bar derivation, exact 15-anchor manifests and amounts, deterministic
selection/ties, late readback, missing minute, time boundaries, native package/
inventory drift, original UUID/hash collisions, source and clock regression,
wrong types/scopes/epochs, exact overlap and previous-history binding, process
epoch retention and the import/side-effect boundary. These tests establish
pure selection/aggregation behavior; they do not prove any real accepted source,
native clock, complete ledger, authenticated transport, hosted path or performance.

The source-only class builds literal original records for 915 minutes and
complete overlap/increment paths; historical fixture clocks are explicit inputs,
not observations of a real provider or native server. Final focused verification
of the new integer-microsecond action policy: **67 cases, zero skips, 51.655
seconds**, comprising 36 prospective source cases and the unchanged 31 acquisition
cases under isolated Python 3.12.14, network denial and
`PYTHON_DOTENV_DISABLED=1`. This includes a valid same-floor fractional action
and separate one-microsecond-before native-readback and original-receipt negatives.
