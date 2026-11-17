# Production paper-v6 implementation — November 17, 2026

This batch connects the existing prospective two-EMA kernel to a maintained
production runtime. It includes original provider bytes and clocks, source
recipe reconstruction, immutable native state/history transitions, owner
controls and a new dashboard. The recorded local checks establish component
behavior; full composed CI, exact deployment and hosted operating acceptance
remain separate.

## Runtime and data

Jupiter Price v3 supplies a SOL/USD reference mark. Mainnet RPC genesis and block
time validate its chain/context. The worker retains the exact three original
responses, then independently reads native acceptance before deriving a mark.
Birdeye is not required for this prospective v6 profile. These observations are
not executable swap quotes or historical provider candles.

The model requires 915 complete observed minutes, builds 15-minute sampled
closes, then evaluates eight equally funded candidates for a full hour. Only
EMA fast3–12 and slow15–60 evolve; other parameters remain fixed. Original
random state, lineage, capital, positions, assessments and transition inputs
are replayed through the existing public mathematical kernel. Protective and
decision calculations share one genuine preparation clock before database I/O.
Original preparation and native commit clocks remain distinct. Fees, half-spread
and slippage are explicit uncalibrated scenario inputs.

The new private `vn_paper_v6` schema uses seven RLS-enabled tables. The runtime
login has only its owner/run-scoped RPC; neither PostgREST exposure nor a browser
admin key is added. Writes retain exact original IDs, wire bytes and compare-
and-swap heads. Unknown acknowledgments use original readback. Native Stop can
retain an exact terminal rejection of a decision so the controller can finish
Stop without guessing that an uncertain write rolled back. A different worker's
already-committed Stop is recovered by replaying its full prefix.

Recovery runs in the background and withholds partial financial projections.
Stop is retained during warmup and recovery. Known archived incomplete provider
attempts permit the next paced sample; uncertain storage remains closed. Derived
state caches and the946-minute source cache are bounded; original evidence is
retained. Native inventories are limited both by rows and8MiB of raw page data.

## Local verification

- Exact28-file candidate adoption verified against its tracked manifest;62 actual
  native PostgreSQL cases passed in622.597s, zero skips.
- The production native journal's expanded14 cases passed in13.781s, including
  scope/ACL, large byte-bounded pages, quota rollback, original replay, Stop races
  and credential expiry while waiting on a real row lock.
- Replay tests cover two complete generations,16 assessments,24 births and held
  positions after restart. Separate service tests cover Stop during background
  recovery, in-flight acquisition, between prepared phases and after a competing
  worker has already committed model Stop.
- Source tests use genuine synthetic original capsules and915/930-minute
  inventories, exact overlap, missing minutes, original clock retention, known
  failed attempts and bounded cache retention. These synthetic minutes do not
  satisfy a production warmup.
- Focused HTTP/transport/factory tests validate owner auth, finite bodies, fixed
  CORS, private-safe errors, TLS/CA/SCRAM/channel binding, cancellation ownership,
  cleanup and original native rejection. Frontend controls and types pass their
  focused checks; full composed verification is recorded at release.

## Deployment and operating limits

Use the existing three Dashboard production projects. `vercel.json` enables
`main` and denies other branches. The tracked exporter now names the
`persisted-production-v1` profile and excludes legacy `railway.json`, private
files and local tools. The operator installs the versioned migration and records
its exact source in the same transaction. It generates one private finite
seven-day login, reconciles uncertain replies without automatic write retries,
and can close only that original login/binding for rollback.

A real provider/native canary must measure the strict receipt-age budget before
pilot acceptance. The initial replacement takes at least975 qualifying minutes
(16h15m), plus alignment, gaps and scheduling. A started worker is not that proof.

A missing minute after an established history is visible as `history_gap` and
cannot be backfilled. Automatic fresh-warmup/run succession and a verified
compact checkpoint remain required for unattended long-term operation. Streamed
recovery still grows with the retained journal. The1GiB budget counts retained
wire bytes, not physical indexes/TOAST/control storage; measure those separately.
Credential authorization is rechecked after the run lock inside the bounded
operation; it is not the laboratory's literal-COMMIT deadline proof.

The new development-only Picomatch advisory remains unpatched. Its exact graph
exception expires November24 00:00UTC; production audit is clean. See the dated
security review and SEC-NOV24 in TODO. Live wallet funding, signing, swaps and
activation require separate authorization and are not part of this runtime.
