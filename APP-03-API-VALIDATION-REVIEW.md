# APP-03 API validation and schema review — 2026-10-13

Read-only source review of committed Dashboard base
`c04be4fb536c593541603a7e7c6c1140771b139d`, performed on isolated branch
`codex/dashboard-api-validation-review`. There are exactly two Next API route
files, exposing test-event GET/POST and sentiment POST. This document changes no
route, application, migration, environment, database, credential or provider.
No API request, database query, browser run or test was performed. The user's
uncommitted migration in the main checkout was neither read nor changed;
migration references below are the committed version in this owned checkout.
Frozen parser commit 5410e91, A1 commit 45d2b7a, model commit 760f155 and Nestegg commit 245f102 branches are preserved.

APP-03 remains a small request/configuration repair with a separate DB-04 schema
reconciliation gate. It does not depend on the evolutionary model/native-source
work and does not close that runtime or the wider audit.

## Confirmed source findings

| Priority / finding | Exact source | Consequence and bounded repair |
| --- | --- | --- |
| P1 — GET limit is coercive rather than validated | `src/app/api/v1/test/route.ts:8`, database use at line14 | `1abc`/`1.5` become 1, invalid text becomes NaN, negative values remain negative, and values above 100 silently clamp. Empty limit silently defaults 50; duplicate limits use the first. Freeze strict ASCII integers 0…100, default 50 only when absent, and reject malformed/negative/oversized/ambiguous values400 before any query. Preserve valid 0 used by existing safe smokes. |
| P1 — Date shape accepts impossible dates | `src/app/api/v1/sentiment/route.ts:56`–65 and98 | `2026-02-29`, `2026-13-01`, `0000-00-00` pass the regex. Depending on the unverified table type, this may store an invalid textual day or become a DB error/500. Validate an actual Gregorian date with explicit leap/year/month/day bounds; preserve omitted-date UTC default. Avoid JavaScript's implicit date rollover and year0…99 constructor remapping. |
| P1 — Test POST accepts arrays; no application payload budget | `src/app/api/v1/test/route.ts:26`–39 | `[]` is truthy and `typeof === "object"`, so it passes the object contract and is inserted as payload. Neither route has an application byte/depth/node budget. Require a non-null non-array JSON object and bounded original input before parsing/querying. Platform request ceilings do not define this application's contract. |
| P1 — Arbitrary test payload can silently change nonfinite values | `src/app/api/v1/test/route.ts:26,37`; installed PostgREST builder `src/PostgrestBuilder.ts:279`–281 | Valid JSON `{"metric":1e309}` is parsed by JavaScript to an infinite number; SDK JSON.stringify serializes that value asnull. The route has no recursive finite-number check, so it can acknowledge altered diagnostic content. Add finite-number checks to the bounded JSON walk; do not introduce a full native financial wire/parser or claim exact preservation of arbitrary high-precision JSON numbers. |
| P1 — API table creation/constraints are not reproducible from migrations | `test/route.ts:11,35`; `sentiment/route.ts:92`; `TODO.md:707` | No tracked migration defines `test_events` or `market_sentiment`. Earlier preflight says both exist remotely. Obtain/review exact columns/defaults/types/constraints/indexes/ACL/RLS/unique constraint provenance later under DB-04; prepare a reviewed forward reconciliation, never blindly create duplicates or replay historical migrations on production. |
| P1 — Authentication/configuration assumptions are implicit | `src/lib/api/auth.ts:6`–8; `src/lib/supabase/admin.ts:5`–8; handler35 | Missing API key currently fails closed (`null !== undefined`); a configured empty key matches an empty header. Supabase non-null assertions are compile-time only: missing URL/service key can throw while importing the module before the wrapper/auth runs. Require a nonempty configured key and controlled private configuration failure, with lazy/guarded admin construction if needed; return a stable unavailable response without raw configuration. Do not rotate or expose secrets. |
| P2 — Errors and protected response handling need a narrow contract | `src/lib/api/responses.ts:11`–20; `src/lib/api/handler.ts:41`–43; test17,44; sentiment105–114 | Responses have no explicit no-store policy; whole unexpected/PostgREST error objects are logged. Platform caching/log behavior was not checked. Add explicit no-store and safe code/request-ID logging. Sentiment maps every 23505 toduplicate date 400; bind that interpretation to the verified specific date constraint, then choose/document conflict semantics. Do not turn infrastructure/schema failures into success/empty arrays. |

The installed SDK source was read locally, not executed or changed. The lockfile
pins `@supabase/postgrest-js`2.117.2 (`package-lock.json:2316`); its
`PostgrestTransformBuilder.ts:492`–501 sets the supplied limit directly as a
string, confirming there is no downstream numeric validation to rely on. SDK
JSON serialization above only specially handles bigint. These are source-level
findings; no new hosted outcome is claimed.

## Authentication, ownership and schema boundaries

Both routes use the same API-key wrapper and server admin client. The admin
module explicitly says it bypasses RLS (`src/lib/supabase/admin.ts:3`). Test GET
has no owner predicate; inserts have no owner field. This currently describes a
global integration/diagnostic API, not an authenticated per-user dashboard API.
The signed-in dashboard layout (`src/app/(dashboard)/layout.tsx:10`–15) does not
protect route handlers. The proxy refreshes Auth but does not deny unauthenticated
requests (`src/proxy.ts:32`–34). Neither fact bypasses the routes' API-key check.

Freeze whether test events are global integration data and sentiment is one
global row per day, or whether either endpoint is meant to be owner-scoped.
Lack of an owner predicate is a real scope boundary, not evidence that a private
row was leaked in this review. A browser session/user-supplied owner UUID must not
be bolted onto an admin query as authority. If global integration is intended,
document its narrow caller/data policy and minimize selected columns. If private
owner data is intended, add verified session/issuer-to-owner binding plus table
and query enforcement in a separately reviewed schema repair. `x-source` is
caller-supplied metadata (`src/lib/api/auth.ts:16`), never authenticated provider
provenance; bound it without treating it as a principal.

The API's local table dependency inventory is:

| Table | Columns the code assumes | Local migration / unresolved schema |
| --- | --- | --- |
| `test_events` | Insertpayload/source; read/ordercreated_at; TypeScript assumesid/payload/source/created_at (`src/lib/api/types.ts:29`–35) | Creation absent; actual types/defaults/id generation/JSON object constraints/payload budget/ACL/RLS unknown in this review. `.select('*')` and `.select()` should become explicit reviewed output columns. |
| `market_sentiment` | score/sentiment/summary/key_factors/date/source; returned type alsoid/created_at (`types.ts:38`–46) | Creation absent; date type, score precision/range, enum, array/null semantics, date uniqueness, indexes/defaults/ACL/RLS must be reconciled. Unknown actual unique constraint must not be guessed from 23505 alone. |

The tracked schema does define owner-scoped profiles, Nestegg, portfolio and
legacy worker tables, followed by the closed v5 migration. These do not supply the
two API dependencies. Preserve already accepted DB-04A parent/exit repairs,
UUID run columns, three-column generation uniqueness and working remote
extensions.moddatetime trigger. The committed historical colony migration's
unqualified trigger (`20260409210000_vonneumann_colonies.sql:39`) is not grounds
to reopen the previously verified trigger defect or edit the user's migration.

Preserve NEST-06A scoped-client/session publication fixes and their pending actual
browser acceptance. They do not authenticate these separate global API routes.
The existing synthetic browser backend permits only authenticated `test_events`
GET with limit=0 (`scripts/browser-fixtures/backend.mjs:138`–142); it does not prove POST,
malformed inputs, table constraints or sentiment persistence. Previous production
zero-row smokes remain valid but narrower than APP-03 acceptance.

## Ordered next implementation proposal

1. **Freeze the route contract and caller scope.** Preserve API-key integration
   compatibility unless a reviewed owner design changes it. Decide strict limit
   grammar, date range, payload/text/factor/header limits, unknown-field policy,
   conflict responses and private configuration errors. Proposed starting budgets
   for review: 64 KiB body, summary 4,096 UTF-8 bytes,64 factors of 256 bytes each,
   source 128 bytes, depth 16 and a bounded node count. These are proposals, not
   silently accepted limits or a new saved-plan/schema requirement.
2. **Implement pure bounded validators plus route wiring offline.** Minimal new
   shared API validation module; reject before creating/calling the DB client.
   Test body is object-only and finite recursively; sentiment fields are finite,
   enum/calendar-valid and bounded. Normalize only explicitly specified text;
   do not silently coerce numeric types. Keep valid limit 0/default 50/max 100 and
   missing-date UTC behavior. This can run alongside source/UI work now.
3. **Harden the common wrapper/configuration/response boundary.** Validate private
   configuration, contain import-time failures, no-store all protected responses,
   safe logging and deterministic errors. Authorized valid requests get normal
   responses; malformed inputs must perform zero DB calls. No broad credential,
   middleware or account refactor is needed for this slice.
4. **Resolve DB-04 separately before schema/persistence claims.** Future exact-
   target read-only catalog review → approved schema manifest/forward change and
   rollback → owned offline PostgREST/constraint tests → explicitly authorized
   target application and verification. Preserve old migration/source history;
   do not infer remote absence from local absence. This blocks full persistence
   acceptance, not steps 1–3.
5. **Prove the chosen contract with synthetic routes and later finite hosted
   acceptance.** Inject/mock the admin interface, cover limit/date/object/finite/
   byte/depth/field boundaries, no-DB-on400/401/503, expected duplicate constraint
   versus other DB errors, exact output projection/no-store and private error
   logs. Existing owned browser fixture is deliberately zero-row-only; extend
   only reviewed synthetic routes for these tests. Any hosted write requires
   exact allowed project checks and an owned cleanup/reconciliation plan first.

Explicit exclusions prevent false findings and scope growth: JSON literal NaN
fails request parsing already; infinite sentiment scores fail the 0…100 comparison,
so adding Number.isFinite is defensive validation rather than a reachableNaN
score exploit. SDK 2.117.2's retry helper excludes POST/PATCH/DELETE
(`fetchWithRetry.ts:109`–112); no automatic SDK POST-retry defect was found.
A lost POST acknowledgment can still be an uncertain write, so future integration
documentation must not promise safe blind retries/new event IDs. This is separate
from adding a full bot-style command journal to these small routes.

No application/API/migration repair is authorized or implemented by this review
document. Root review should select the first bounded validator/configuration
batch and keep table provenance/owner semantics explicit prerequisites.
