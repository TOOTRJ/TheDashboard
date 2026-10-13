# Bounded Dashboard integration API contract

## Integer-score alignment version — 2026-10-13

The original reviewed implementation is frozen at commit
`70a075e196ebc5b175e0c290776892d40286c029`. That version deliberately accepted
finite fractional sentiment scores under its then-unverified schema. This new
source version adds one rejection-only integer-value check, without changing
the original commit or the other request/authentication/response rules.

The separately recorded read-only catalog observation
`supabase/audits/2026-10-13-api-schema-readonly.json`, SHA-256
`25d9362d0c22df79f54898cf15933e522a65f0ec479db76205d35d489d53012f`,
records exact target `The Dashboard` / `fxpxsciltakyypunglzr`, organization
`cqfnnaunmupdyobkyqfo` / `Valentine Jester`. Its query digest is
`f8e55c02443138d7685e73e64e2b693690bdad81d6dab89d16ed838870872614`.
Root performed that target-verified query; this implementation only read the
existing receipt and performed no additional catalog or provider request.
The observation read catalog metadata only, no row data, and changed no schema
or ACL. It establishes `market_sentiment.score` as integer with a 0…100 check.

Scores must now be finite integer **values** 0…100. Fractions, booleans,
strings and nonfinite parsed values are rejected before client creation or DB
access; nothing is rounded or coerced to an integer. Ordinary normalized
JavaScript JSON semantics are retained: integral `1.0` and `1e0` are accepted
as 1, and negative zero is accepted as zero under JSON serialization. The
pure validator does not mutate a negative-zero input. This is not a JSON
token-lexeme, sign, decimal precision or native financial-wire parser.

This APP-03 implementation follows the historical read-only findings in
`APP-03-API-VALIDATION-REVIEW.md`, based on committed source
`c04be4fb536c593541603a7e7c6c1140771b139d`. That report records the original
defects; its statement that no repair was implemented applies to that earlier
review, not this new slice. No schema, owner authorization, environment value,
credential, provider, account, wallet, economic engine or hosted data changes
are made here. The global API-key integration scope is preserved.

Both `/api/v1/test` and `/api/v1/sentiment` authenticate before their handlers.
An absent/blank configured integration key produces fixed 503/SERVICE_UNAVAILABLE;
with a valid configured key, missing/incorrect caller headers produce 401.
Whitespaces are not silently trimmed into a different credential. Private
Supabase configuration is checked and the admin client created lazily only
after authentication and input validation. Successful clients are cached only
inside this server process against its URL/key configuration; a missing or
failed new configuration cannot fall back to a stale cached client. Client auth
persistence, refresh and URL session detection are disabled. Configured values,
SDK instances and raw exceptions never enter error responses or logs.

The admin client still bypasses RLS and performs the existing global integration
operations. No user-supplied owner ID, browser login, x-source label or payload
field becomes authorization. The separate dashboard session and fixed
native-source/model scopes retain their existing meaning.

## Exact request and response rules

| Input | Accepted contract |
| --- | --- |
| Test GET limit | Absent = 50; exactly one canonical ASCII integer 0…100, including 0. Empty/duplicate/prefix/fraction/signed/leading-zero/oversized values are 400 before client creation or query. |
| JSON body | At most 65,536 original UTF-8 bytes, read incrementally without trusting Content-Length; non-null non-array object; at most 16 nested containers and 10,000 value/key nodes. Empty chunks are not copied/retained. Oversized input cancels the reader best-effort and rejects 400; locks are released without replacing the original failure. |
| All JSON values/keys | Parsed numbers must be finite. Strings/keys reject NUL and lone surrogates; valid supplementary Unicode is retained. JSON parse/UTF-8/read failures are safe 400. Ordinary JSON normalization/JavaScript number semantics remain; arbitrary high-precision numbers and duplicate-key spelling/raw bytes are not preserved as a financial source wire. |
| Sentiment fields | Exactly score/sentiment/summary/key_factors with optional date; finite integer-value score 0…100, without rounding/coercion; enum bullish/bearish/neutral; nonempty summary ≤ 4,096 UTF-8 bytes; at most 64 string factors, each ≤ 256 UTF-8 bytes. Empty factor strings remain compatible. |
| Sentiment date | Actual Gregorian YYYY-MM-DD, year 1…9999, correct leap/month/day rules; omission defaults to the current server UTC date. No implicit rollover or year 0…99 constructor remapping. |
| x-source | Absent/empty = "unknown"; otherwise ≤ 128 UTF-8 bytes, no control/NUL/lone-surrogate characters. It remains caller metadata, not provider/principal attestation. Checked before DB access on both GET and POST. |

Every protected 200/201/400/401/409/500/503 response explicitly sets
`Cache-Control: no-store`. Standard response metadata timestamps remain.
Validation failures are 400/BAD_REQUEST. Missing/unusable private configuration
is fixed 503. Unexpected/database errors are safe 500 with only a fixed failure
category logged. Every 23505 is generic 409/CONFLICT, “A record conflicts with
existing data”; no unverified date constraint is guessed. No automatic POST
retry or reconciliation mechanism is added.

Reads request explicit `id,payload,source,created_at` test-event columns, and
sentiment inserts request explicit `id,score,sentiment,summary,key_factors,date,
source,created_at`. These reflect the existing route types and minimize default
star selection. The recorded catalog now confirms those columns, integer
score, date type and named `market_sentiment_date_key`; it does not prove
persistence or reconstruct missing tracked creation migrations. Source and
created_at are nullable in both tables. Future row validation must retain
legitimate null values rather than invent source labels or timestamps.
DB-04 still must reconcile both remotely observed tables with the missing
tracked creation migrations and separately review table ACLs. A malformed input
never gets turned into an empty-success query result.

Successful GET acknowledgment requires an array response. Successful insert
acknowledgment requires a non-null non-array object from `.single()`. A null,
missing, scalar or wrong-container response with no SDK error is a fixed safe
500, after one original query. The response does not trigger another request or
claim that an insert was rolled back or absent. These checks establish response
presence only; returned row fields/types and actual persistence/constraint/
ownership acceptance remain unproved by this mocked slice. A lost POST
acknowledgment can remain uncertain. Do not promise
safe blind retries, duplicate-date idempotency or durable original-command
reconciliation without a separately reviewed contract and schema.

## Offline verification and limits

The final focused suite executes the actual transpiled validators, routes,
wrapper, response helpers and lazy admin implementation with injected Next/SDK
interfaces, fake configuration and network denial. The integer-alignment
version passes 28 cases, zero skips, in 1,980.600541 ms on pinned Node 24.19.0.
The previous 27-case result (1,690.385 ms) is historical and does not cover the
integer-only change. The new actual-route case rejects fractions/nonfinite/
boolean/string/null scores with zero DB/client calls and accepts exact 0/1/100,
integral decimal/exponent forms and negative zero without rounding. Fixtures
also cover exact 0/default/max
limits and malformed forms; unauthorized/configuration ordering; object/finite/
UTF-8/Unicode/depth/node boundaries; calendar/field/source limits; selected
columns; generic conflict and safe private errors; configuration-aware cache
replacement; and no-error null/wrong-container acknowledgments. The response
presence regression exercises 18 mocked replies across the three actual route
operations, each with one original database call and no retry. No app env file,
real credential, Supabase project or live request
was loaded. These mocks prove route choreography, not actual deployed database
behavior or complete browser acceptance.

A controlled 20,000-empty-chunk regression holds the eventual original JSON
body and traps any empty-chunk copy. It observes zero copies/client construction/
DB calls before full body completion, then one accepted request. The earlier
25-case results are historical; peer review corrected empty-chunk retention
without imposing a new segmentation/chunk-count restriction. Byte/depth/node
budgets are not a request-duration deadline, platform upload-buffer/RSS limit,
or protection against every slow-client/resource scenario. The corrected
26-case result (1,226.769667 ms) preceded the separate response-presence repair
and is historical; the 27-case result includes both corrections but precedes
this separately recorded integer-value alignment.

Whole-project TypeScript and focused validation/test lint passed on the
integer-alignment source. The
earlier reviewed production build passed in
21,172.829458 ms before the response-presence repair, including a clean locked
install in the existing helper's owned copy of 155 allowlisted files /
1,361,478 bytes. The normal tracked frontend inputs were
augmented with exactly the two new regular source helpers, `errors.ts` and
`validation.ts`, without staging them or changing the worktree index. Its
child environment used pinned Node 24.19.0, private empty npm configuration
files/cache and deliberately fake Supabase values. App environment, SSL,
cloud/agent configuration and shared node_modules were not copied. Both
integration API routes were included in the resulting build. This establishes
frontend build compatibility, not live DB or production API acceptance.

That earlier exact temporary directory `/private/tmp/dashboard-ci-build-2uvRgb`, owned
by marker `39d857a5-b4e6-4e57-b717-a877464a06be`, was removed through the helper's
marker check, and its absence verified after cleanup. The isolated install
reported an ESLint 9.39.5 lifecycle deprecation warning; package versions and
shared tools were not changed as part of this validation slice. Package
lifecycle/upgrade review remains separate from the successful build result.
The source-changed build repeat after the response-presence repair also passed,
in 18,882.706708 ms including clean locked installation, with 155 allowlisted
files / 1,361,859 bytes and the same two explicitly reviewed helper inputs.
Both API routes were built. The new directory
`/private/tmp/dashboard-ci-build-foZExI`, marker
`0de2d432-38e6-4028-a9e4-7a758a19dec6`, was removed through the same exact
ownership check and its absence verified. The worktree index remained unchanged.
No shared node_modules install, process, configuration or credential changed.
Root and security peer completed local review of the original corrected
implementation, response-presence checks and contract before commit 70a075e.
Root and security peer completed review of the integer-alignment source,
contract and DB-04 proposal with no remaining blocker within this narrow scope.
Only the exact four-file local commit is authorized; a new full build is deferred
to later integration. No remote rollout, schema/ACL application or migration is
implied.

## Source bindings

These SHA-256 bindings cover the final corrected implementation and focused
tests. This contract is separate from the source bytes and grants no
installation/runtime authority.

| File | SHA-256 |
| --- | --- |
| src/lib/api/errors.ts | a59436fadc29515af368b9d0d5f4425880a4b98385dc4902189ec57ce1969e61 |
| src/lib/api/validation.ts | 04b6b7a9d836dd7e7ef3b0616661450e41b50728a420ee1bc58566eac6a25faa |
| src/lib/api/auth.ts | 9fb1291180f633c02b94990f27ee93778a8846b883017895bebb2a1101b468d8 |
| src/lib/api/handler.ts | d2b02bc7f30f8c3da7fbdc541c59ea30d302a7d9c5a1767998c8d46fb3740dc6 |
| src/lib/api/responses.ts | 23089813778660e1b40e0a754a0d526107199c067167d684b3ea1899290db74a |
| src/lib/api/index.ts | ec9b90eb9b6e419f0708e2cc7db1951fef3b49340ca3c0aad11ff2cbd1de5ddd |
| src/lib/supabase/admin.ts | f7fa201939ecb1a9ba940fb7adbd3919be2967508c790b2a4f54c7569a6a0dfe |
| src/app/api/v1/test/route.ts | 0fe69728777a1030c181e5ff26cba753d700f4c8ed778e421fb1e4ba8011dca4 |
| src/app/api/v1/sentiment/route.ts | 5c337cb184309c7688b3aaf72d0b745567031f6a292a2669f6e724b5a5fd0838 |
| tests/api-validation.test.mjs | c74e974d6a491e46c330d2fe8a0edce16063ab3e5aad3ac6406920c0c3d40785 |
