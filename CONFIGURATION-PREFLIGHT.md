# Dashboard configuration and access preflight

Date: 2026-09-29. Scope: the local Dashboard checkout, Vercel **`the-dashboard`**, and Supabase **`The Dashboard`**. This report accompanies [TODO.md](TODO.md).

**Last verified production baseline before DB-03A2D3B2C1 (2026-10-06): [PR #47](https://github.com/TOOTRJ/TheDashboard/pull/47) is merged; the production alias served READY deployment `dpl_BBoWCHdzJ2NEkA92S3SxoyJkR9PW`, built from merge `dc1e0c02d756ce4412acd79b2c7153fc12e2c985`, with four read-only application checks passed.** Sections 49–53 record transport/projection/legacy, installer and canonical fresh v5 rehearsals; section 54 records native-session authentication. Immutable release results belong in each PR. Next.js remains 16.3.8. The Python worker is unhosted; actual bounded SQL transport/hosted credential and TLS setup, durable legacy evidence/full migration, service/browser selection, hosted acceptance, production timing, safe interruption, preview isolation and hosting remain open. Only the projects pinned in [AGENTS.md](AGENTS.md) are authorized. Historical sections retain dated findings; later verified sections supersede earlier state.

## 1. Exact project scope and available access

| Provider | Required project | Verified identity and access | Decision |
|---|---|---|---|
| Supabase | `The Dashboard` | Project ref **`fxpxsciltakyypunglzr`**; organization **`cqfnnaunmupdyobkyqfo`**, displayed name **`Valentine Jester`**; region `us-west-2`; management API status `ACTIVE_HEALTHY`. Authenticated CLI project metadata returned exactly one matching name. Local link marker, Next.js URL, and Python URL all match this ref. | This is the only allowed Supabase target. Read-only Auth/PostgREST checks succeeded. Reverify name/ref/organization immediately before any future write. |
| Vercel | `the-dashboard` | Verified ID **`prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`**; owning team **`team_8iNNxiNjrOseD4gdSCHkQEzF`**, slug **`orderoftheredjester`**, displayed name `redjester`. Authenticated through dedicated profile `/Users/redjester/.config/vercel-dashboard-codex`. Project API independently confirms ID/name/account ownership. | This is the only allowed Vercel target. The local ID-only link was rechecked with `vercel project inspect`. Continue using the dedicated profile and explicit team/project IDs. |
| Installed Supabase connector | Must match `The Dashboard` before use | The connector's identity getter returned a different project reference, which does **not** match the allowed project. | Stopped using this connector after the identity getter. No tables, records, SQL, logs, keys, or settings were requested through it. Use a correctly scoped connection or the independently verified CLI/API route for this project. |

Minimal account/project identity metadata was used to resolve the intended targets. No other project's application data or configuration was inspected, and no remote project was edited. A service secret accepted by PostgREST is evidence of that credential's access; it is not a complete audit of management-role permissions or row-level security.

Direct target references: [Supabase project](https://supabase.com/dashboard/project/fxpxsciltakyypunglzr), [Verified Vercel project](https://vercel.com/orderoftheredjester/the-dashboard). The Vercel project path now resolves to the verified project. Public app domain: [the-dashboard-chi.vercel.app](https://the-dashboard-chi.vercel.app).

## 2. Credential results from read-only preflight

Tests used existing local credentials in request headers wherever supported. Requests were read-only, redirects were disabled for credential-bearing requests, and outputs were restricted to status/schema/results. Helius's documented RPC URL carries its API key in a query parameter; that URL was not printed or saved. No token values, fingerprints, or response bodies containing secrets are recorded here. Provider checks used local credentials. The follow-up Vercel inspection independently decrypted its four configured variables in memory and confirmed they all match the local values; no secret files were pulled or overwritten.

| Local variable / integration | Current app use | Observed result | Required action |
|---|---|---|---|
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Next.js browser/server auth | Modern publishable-format key accepted by the verified project's `/auth/v1/settings`, HTTP 200. Email and Google auth are enabled. The legacy variable name does not make the modern key stale. | Keep the correct project pairing. Production values match; verify OAuth redirect settings before auth deployment. Actual user login/session flows and RLS still need application tests. |
| `SUPABASE_SERVICE_ROLE_KEY` | Next.js admin APIs and Python persistence | Modern secret-format key accepted by the verified project's PostgREST schema endpoint, HTTP 200. Root and worker copies match. | No invalid-key evidence. Keep server-only. Fix the schema mismatch below; a new key would not fix it. |
| `JUP_API_KEY` | Current paper-trading price feed | Price V3 returned HTTP 200 with positive prices for all eight configured assets. A separate check with the app's `aiohttp` request style also returned all eight. Root and worker copies match. | Retain for the current feed; enforce freshness, rate-limit/error handling, and provider contract tests. This does not validate future swap execution entitlement. |
| `BIRDEYE_API_KEY` | OHLCV warmup and volume | Actual `/defi/ohlcv` capability returned HTTP 200, provider success, and five recent SOL candles. Root and worker copies match. | No stale-key evidence. Validate full historical coverage, limits, timestamps, and volume semantics before research comparisons. |
| `VN_API_KEY` | Worker REST authentication; incorrectly referenced in client code | Present; root and worker copies match. Both local health and protected status requests failed with connection refused because no worker was listening at the configured endpoint. | Credential validity is **unverified**, not rejected. Establish the intended worker deployment and repair the auth design before a controlled readiness test. |
| `API_SECRET_KEY` | Next.js `/api/v1/test` and sentiment API | Decrypted Vercel value matches local configuration. On the verified public domain, an unauthenticated zero-row GET returned 401; the same GET with the key returned HTTP 200, success, and zero rows. | Accepted by the currently served app and its database read path. No POST or data mutation was used. Review environment separation before preview deployment. |
| `HELIUS_API_KEY` | Not consumed directly; a worker RPC URL is configured separately | Initial `getHealth` passed. On 2026-09-30, read-only `getGenesisHash` and six unique `getBlockTime` calls also passed against the fixed Helius mainnet host. | These methods work with the existing key. Set the worker's private `VN_SOLANA_RPC_URL` explicitly; no account credential or environment value was changed by the check. Quotas/continuous operation remain unverified. |
| `VN_SOLANA_RPC_URL` | Newly required by the paper-mode source-time adapter | The code requires an explicit HTTPS endpoint and verifies its full mainnet genesis hash before accepting block times. | Configure only in this worker's environment, never `NEXT_PUBLIC_*` or shared shell/account settings. The URL may contain a private API key; do not paste it into chat, logs, source control, or browser configuration. See section 15. |
| `OPENAI_API_KEY` | No source consumer | Authenticated model-list request returned HTTP 401 with an invalid-key error. | Replace only if an intended feature will use it; otherwise retire it from this project's configuration after checking ownership/dependencies. It is not a current bot-runtime blocker. |
| `XAI_API_KEY` | No source consumer | Model-list request returned HTTP 200 with the expected list schema. | Valid for model listing; generation permissions, balances, and model-specific access were not tested. No current need to update it for the bot. |
| `LUNARCRUSH_API_KEY` | No source consumer | Documented bearer-auth coins-list request returned HTTP 200 with one data item and no API error when using an explicit application user agent. | Working for the tested endpoint. A default `urllib` request received 403, so transport/header behavior must be distinguished from credential validity. |
| `COINDESK_API_KEY` | No source consumer | Current `/admin/v2/rate/limit` returned HTTP 200, no API error, and key-attributed `Data.API_KEY` usage information. | Accepted by this provider; individual market/history entitlements remain untested. |
| `MESSARI_API_KEY` | No source consumer | Metrics v2 lending request returned HTTP 403: `missing required API permission: metric_protocols_permission`. | Resolve the required product/plan only if this feature is needed. This is a permission failure, not evidence that the key is expired or invalid. Do not purchase an upgrade as part of this preflight. |
| `COINGECKO_API_KEY` | No source consumer | Pro account-usage endpoint returned HTTP 400 with guidance referring to the Demo API host. | Confirm whether this is a Demo key and validate against its account/plan. Do not classify a wrong-host result as a universally invalid key; public `/ping` success alone is not adequate validation. |
| `CRYPTOPANIC_TOKEN` | No source consumer | Not transmitted: current plan-specific endpoint contract could not be verified from accessible official documentation. | Confirm issuer account, plan, and current documented endpoint before testing or integrating. |
| `CAESAR_API_KEY` | No source consumer | Not transmitted: variable name alone does not establish the key's issuer. | Confirm the provider and intended feature before sending the credential anywhere. Caesar Data has an official SDK, but that is insufficient proof of this local key's provenance. |
| `TRADINGVIEW_WEBHOOK_SECRET` | No source consumer | Present; no matching webhook handler or external authentication check exists in this code. Current TradingView UI uses public widgets. | Identify the intended inbound integration or retire the unused local setting after checking dependencies. It cannot be evaluated as a vendor API key. |

The installed JavaScript Supabase SDK also completed zero-row `vn_colonies` reads with both the publishable and secret key (HTTP 200). The installed Python Supabase SDK, version 2.28.3, completed the same zero-row read with the worker's secret. This confirms compatibility with these installed SDKs, beyond raw HTTP acceptance; it does not exercise writes or prove user isolation.

The definite invalid key found is **OpenAI**. Several others are accepted, permission-limited, unused, or still unverified. Do not rotate account-wide credentials merely to tidy this project: shared keys may affect other projects, which are outside scope. Prepare project-specific replacements only where a supported integration needs them, and keep secret entry out of chat and source control.

## 3. Confirmed application and database blockers at preflight

1. **Missing `vn_probes.parent_ids` is a current persistence blocker.** The remote schema omits it, and a zero-row `select=parent_ids&limit=0` returned PostgreSQL code `42703` (undefined column). [The repository](services/vonneumann/vonneumann/db/repository.py) unconditionally includes this field when inserting a probe; at preflight it caught/logged write failures (now fixed locally under REL-01). Such inserts would fail against the observed schema. The local untracked draft `supabase/migrations/20260418120000_vonneumann_parent_ids.sql` appears intended to add it. It remains outside the current PR pending DB-04 review of history, ordering, target, and rollback. No migration or write was performed. Backlog: DB-04, REL-01, DB-02.
2. **Existing remote tables and repository migrations do not fully agree.** The verified project exposes `vn_colonies`, `vn_probes`, `vn_trades`, `vn_fitness_snapshots`, `vn_generation_stats`, `portfolio_accounts`, `nestegg_scenarios`, `profiles`, `test_events`, and `market_sentiment`. The latter two exist remotely even though their creation is missing from the inspected migrations. This corrects any earlier inference that they were necessarily absent remotely. Reconcile schema history; do not create duplicate tables blindly. Remote check constraints, triggers, policies, and migration history were not exhaustively inspected by this metadata check.
3. **Browser-to-worker authentication is broken by design.** Client code reads the server-only `VN_API_KEY` name and falls back to a different hardcoded value than the worker. Updating a private Vercel variable cannot inject it into browser JavaScript. Use a session-authenticated server proxy or scoped user-token protocol. Never solve this by exposing the shared privileged key through `NEXT_PUBLIC_*`. Backlog: SEC-01 through SEC-03.
4. **The WebSocket path bypasses authentication and ownership.** The server accepts connections and commands without the REST credential, and broadcasts are not user-isolated. Updating REST keys alone cannot secure it. Backlog: SEC-01/SEC-02.
5. **Worker topology is unresolved.** Local configuration points to HTTP `localhost:8765` and WS `localhost:8765/ws`; read-only local checks were refused. This does not establish whether a remote worker exists. The source CORS allowlist admits only localhost/127.0.0.1 on port 3000. A deployed dashboard needs an explicitly verified reachable HTTPS/WSS worker or the chosen proxy architecture, with the correct origin policy. Backlog: ACCESS-03, SEC-03, SVC-02.
6. **Health currently means liveness, not readiness.** The worker health route does not verify database schema/credentials or feed freshness. A successful health check would not prove the bot can persist probes or obtain fresh tradable observations. Several advertised `VN_*` environment controls are declarations with no runtime consumers. Backlog: ACCESS-03, REL-01, SVC-02.
7. **The evolutionary correctness defects remain.** Valid data keys do not resolve funding extinction, optimizer cohort/selection faults, faulty metrics, timestamp/timeframe handling, risk-stop behavior, or frictionless fills. Repair these before comparing strategies. The updated backlog adds FILL-01 and moves the data/persistence foundation ahead of the two-gene experiment.

## 4. Environment and deployment evidence

| Component | What was established | Still required |
|---|---|---|
| Local Next.js configuration | Root `.env` is ignored/untracked. Supabase URL matches the allowed project; local worker URLs remain localhost. Ignored `.vercel/project.json` now contains only verified project/team identifiers. | Local frontend/worker smoke tests after repairs. Neither runtime was started during preflight. |
| Local Python configuration | Separate ignored, untracked service `.env`; Supabase URL matches Next. Supabase secret, VN key, Jupiter key, and Birdeye key match their root equivalents. | A documented startup environment, effective configuration validation, and process restart plan after later changes. |
| Supabase | Correct project/name/org verified; local and Vercel Supabase values match; SDK/Auth/PostgREST reads accepted; table/column facts above confirmed. | Migration history, RLS/ownership tests, OAuth Site URL/redirect allowlist, schema constraints, and controlled round-trip tests remain release checks. |
| Vercel frontend | Dedicated login, project/team ID, local ID-only link, four environment values, public domain, current served deployment, and Git repo/branch verified. Login GET 200; unauthenticated root redirects to `/login`; authenticated API zero-row GET 200. | Two latest deployment attempts are ERROR, and no worker HTTP/WS endpoints are configured in this project. Build failure details and worker hosting remain implementation/release tasks. |
| Remote worker/WebSockets | No verified remote worker URL/deployment was found in local source/configuration. | Locate the intended deployment from approved project metadata, then read-only health/auth/CORS checks. Do not start a colony to discover connectivity. |

Previous audit check results remain a historical baseline, not new runs in this preflight: TypeScript passed, lint failed with a WebSocket declaration-order issue and warnings, 31 Python source files parsed, substantive Python regression tests were missing, and npm reported 15 vulnerabilities. Re-run appropriate current checks when implementing SEC-05 and QA-01. Preserve the 18 pre-existing tracked-file modifications, edited historical migration, untracked parent-ID migration, and existing local working directories.

The system Python used for the SDK check was Python 3.9 with LibreSSL 2.8.3; `urllib3` emitted an OpenSSL compatibility warning, although the Supabase read succeeded. Specify and lock a supported Python/TLS runtime for the worker instead of relying on this incidental system interpreter. No worker process was running, so this is not a claim about an existing production runtime.

## 5. Verified Vercel deployment/configuration findings

- The four configured variables are `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `API_SECRET_KEY`. All target production, preview, and development, with no branch-specific override in the returned metadata. Explicit decrypted-value reads confirmed every value matches local configuration and has no surrounding whitespace. Initial list responses contained encrypted envelopes; those ciphertext strings were not used as credential-comparison evidence.
- Preview and development currently share production's Supabase URL and credentials. A preview deployment is therefore not an isolated database test environment. Keep initial tests mocked/offline; resolve preview database access before any test that writes.
- No `NEXT_PUBLIC_VN_API_URL` or `NEXT_PUBLIC_VN_WS_URL` is configured in the project. Current source would fall back to localhost if built with this configuration. This is a deployment gap, not a stale-key diagnosis. Jupiter/Birdeye credentials belong in the worker's environment; their absence from the frontend Vercel project is not itself a defect.
- Vercel's stored Git label is `biggrizzly11/TheDashboard`, production branch `main`. GitHub now resolves that address to canonical `TOOTRJ/TheDashboard`; both identify repository `1141090963`, which also matches Vercel's stored repository ID. The local origin was updated to `https://github.com/TOOTRJ/TheDashboard.git` for the authorized PR workflow. Project framework is Next.js and configured Node runtime is `24.x`; Vercel's stored Git label was not edited.
- Latest production attempt: `dpl_7Xf5P1wH9UvCkN8ywAtVfWAaG7GF`, URL `the-dashboard-nprks9u6u-orderoftheredjester.vercel.app`, commit `254cdbab0958d5dc28b0f7c13ce8c8f5b64b6ccb`, state **ERROR**. The preceding attempt is also ERROR. The inspected deployment metadata did not include an error message, and the CLI log request did not return a diagnostic build failure; the cause remains unverified.
- The older ready deployment is `dpl_w6f9JzQ59syDqEExozGaLcGXHKnE`, URL `the-dashboard-kdzdn1eot-orderoftheredjester.vercel.app`, commit `2354ccf8d142aa37808b9f86e67aa1617286a9ce`. The current project domain is `the-dashboard-chi.vercel.app`. Domain ownership was checked before sending an application API key.
- Public smoke checks: `/login` returned 200; `/` returned 307 to `/login`; `/api/v1/test?limit=0` returned 401 without credentials and 200/success/zero rows with the matching app key. No signup, login submission, password-reset email, colony start, or data write was performed. The team-suffixed alias redirected to Vercel SSO; its protection was not changed.
- Installed CLI 60.0.0 `vercel link` can refresh local OIDC environment data and migrate configuration. To avoid those extra effects, the verified IDs were written directly to the ignored `.vercel/project.json` and independently checked with `vercel project inspect`. No `.env.local` was created or altered by this setup.

## 6. Implementation handoff and release gates

The access assessment is complete for local repairs. Missing worker deployment, migration validation, preview isolation, and failed builds are recorded work items; a completed assessment does not assert that those systems are ready.

1. **The approved local security, validation, and reliability slices are implemented.** Existing Supabase user sessions supply identity, REST and WebSocket paths enforce ownership, browser shared-key defaults are removed, and controls target explicit colony IDs. The continuation adds SEC-04 validation/lifecycle handling, REL-01 error reporting, and the current SEC-05 dependency repair described in section 8. SEC-05 remains open for the announced Next.js security release. Real-session, browser, and deployment checks remain release work.
2. **Preserve the baseline and isolated tooling.** The 18 pre-existing tracked-file modifications and untracked user artifacts remain. Review focused patches for rollback; do not reset the working tree. Use the dedicated Vercel profile, pinned project/team IDs, project-local dependencies, and owned processes/ports as described in AGENTS.md.
3. **Reconcile Supabase schema state** before service-backed tests: inspect migration history and prepare the `parent_ids` forward migration and verification procedure for `fxpxsciltakyypunglzr`. Prefer corrective forward migrations for rollback; assess data effects and recovery before applying. The unrelated connector remains excluded.
4. **Repair and validate the deployment path.** Reproduce the current build in isolation, investigate the failed attempts, configure the chosen authenticated worker topology, and resolve preview database isolation. Retain the previous ready deployment as a candidate rollback point, but verify rollback compatibility with any schema changes before release. No push/deploy/promotion occurred here.
5. **Resolve remaining credentials only when needed.** Current Supabase/Jupiter/Birdeye/API-secret checks do not justify replacement. VN user-facing shared-key auth is being replaced by the planned session-auth design; its worker runtime was unavailable. OpenAI, Messari, CoinGecko, CryptoPanic, and Caesar follow-ups remain as documented, without changing shared credentials.
6. **Continue TODO dependencies and prepare the release review.** Include tests, exact target IDs, migration/environment changes, rollback steps, and configuration validation. Live signing, funding, swaps, and trading remain outside this work.

## 7. Approved local security batch — configuration contract

The user manually confirmed the two project identities, authorized another read-only verification, and then explicitly approved local security and colony-control changes plus offline tests. Cloud changes, migrations, credential changes, deployments, and trading were excluded. The following contract supersedes the old shared-key behavior described in the historical findings above.

- **HTTP identity:** protected worker routes require `Authorization: Bearer <Supabase user access token>`. The worker verifies the token using its fixed configured Supabase Auth `/auth/v1/user` endpoint, with bounded asynchronous requests, no redirects, and no inherited HTTP proxies. The authenticated user determines the owner; client `user_id` is rejected. The old worker `VN_API_KEY` is no longer used and must not be made public. Existing environment files have not been edited.
- **WebSocket identity:** the exact browser origin must be allowed. The first frame is `{ "type": "auth", "access_token": "<user access token>" }`, followed by server acknowledgement `{ "type": "auth_ok", "data": { "user_id": "<verified user>", "expires_at": 0 } }` (the real expiry is a future Unix timestamp). Only then is the connection eligible for that owner’s events. Tokens never go in the URL. Connections expire with the access token; refreshed sessions reconnect and local logout retires the old connection. WebSocket commands are disabled; use the authenticated colony-specific HTTP routes.
- **Compatibility:** `/api/v1/status` returns only the authenticated owner’s latest colony. `/api/v1/simulation/start` retains session-authenticated creation. The old global simulation pause/resume/stop routes return 410. Existing external clients must switch to `/api/v1/colonies/{id}/{action}`. Health exposes basic liveness without user or colony counts.
- **Worker configuration before a controlled run:** set `VN_ALLOWED_ORIGINS` to exact, comma-separated dashboard origins. An empty value allows no browser origins. For a local frontend at port 3000, an example is `http://localhost:3000,http://127.0.0.1:3000`. Production must set `VN_ENVIRONMENT=production` and allow only the intended HTTPS dashboard origin. Wildcards, credentials, URL paths, query strings, and public plaintext HTTP origins are rejected. These examples are instructions for a later setup step, not changes already made.
- **Supabase authentication key:** existing worker `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` remain server-only. `SUPABASE_PUBLISHABLE_KEY` or `SUPABASE_ANON_KEY` may optionally supply the Auth request’s API key; otherwise the existing server key is used. No new key or rotation is required for offline verification.
- **Frontend configuration before deployment:** set both `NEXT_PUBLIC_VN_API_URL` and `NEXT_PUBLIC_VN_WS_URL` to the reviewed HTTPS/WSS worker endpoints. The local code disables worker access with an explicit setup error when production settings are absent or unsafe. Localhost defaults are restricted to development. Current Vercel settings have not been changed.
- **Login callback:** redirects resolve against the actual request origin and accept only safe relative destinations. The callback no longer trusts a raw `x-forwarded-host` value. Any later reverse-proxy deployment must provide the correct canonical request URL; do not fix a proxy mismatch by accepting arbitrary forwarded hosts.

Browser logout cleanup is not a claim that every already-issued JWT is immediately revoked across all clients. Supabase documents access-token validity through expiry; actual login, logout, refresh, and policy behavior still require controlled integration verification. See the official [getUser verification contract](https://supabase.com/docs/reference/javascript/auth-getuser) and [sign-out behavior](https://supabase.com/docs/guides/auth/signout).

Offline verification uses fake credentials and provider responses, in-process HTTP/WebSockets, fake repositories/controllers, and network-denial guards. No running worker, database write, or real user session is required. Run from the repository root with the existing local runtimes:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 PYTHONPATH=services/vonneumann python3 -m unittest discover -s services/vonneumann/tests -t services/vonneumann -p 'test_*security.py'
node --test tests/*.test.mjs
./node_modules/.bin/tsc --noEmit --incremental false
./node_modules/.bin/eslint src tests
```

Final local results: **50 Python tests and 23 Node tests passed (73 total)**; TypeScript passed. Focused lint covering changed source and tests has zero errors and 15 pre-existing unused-variable warnings. Broad `eslint src tests` reports seven errors in unchanged files (`strategies/page.tsx`: six render-created `SortIcon` instances; `dashboard/Charts.tsx`: one render-created `CustomTooltip`) and 36 warnings. These failures are recorded in QA-01, not reported as a clean project-wide lint run. Node emits a module-type detection warning during native TypeScript tests; the known system-Python LibreSSL warning also remains. Package/module configuration and system runtimes were not changed to suppress them.

The minimal UI-01 selection boundary is repaired. UI-02 still needs same-colony event/snapshot reconciliation: an older database read can overwrite newer socket data, and a delayed control response can overwrite a newer status event. These display-freshness issues are distinct from cross-user/cross-colony access and selection protection.

These checks do not replace a production build, a browser end-to-end test, remote RLS verification, or migration/deployment review. Worker hosting, preview data isolation, the missing `parent_ids` column, and the evolutionary-engine defects remain separate backlog work.

## 8. Local validation, reliability, and dependency continuation

The user's approval to continue was used for local source/dependency repairs and isolated verification. No Vercel or Supabase mutations, deployments, migrations, credential changes, environment-file edits, live trades, or changes to the other agent's project were performed. The allowed target identities and dedicated CLI rules above remain the boundary for later cloud work.

**Launch validation and lifecycle:** the worker and dialog reject unsupported modes, strategies, presets, genes, assets, nonfinite values, invalid integer/boundary inputs, insufficient starting capital, impossible gene relationships, and zero reproduction intervals. Live mode is rejected. Zero mutation, explicit nulls, and cleared preset overrides survive request parsing; the engine's fixed/disabled-gene behavior still requires ENG-08. Differential evolution requires at least four initial candidates. Validation happens before colony persistence or feed creation and returns a sanitized 422 response.

A valid start first persists `starting`, then awaits initial probe writes, usable positive finite prices, and strategy initialization. Only a successfully persisted transition to `running` permits the supervised loop to begin. Preparation has a 30-second deadline; cancellation drains any in-flight database write before attempting the terminal state. This is lifecycle coordination, **not a multi-table database transaction**: partially written records are retained and may need reconciliation. An unacknowledged write is not proof that the server did not commit it.

Startup, tick, persistence, and configured provider failures reach a terminal `failed` state with safe error codes. Feed resources and background tasks are cleaned up. Failed/stopped records remain owner-visible. Accepted controls complete their durable transition even if the HTTP caller disconnects; refresh status before retrying. Normal stop waits for the current tick/event batch, subject to a deadline, then closes resources. A racing tick failure cannot be relabeled as a successful stop. Positions and partial ledger records are retained for reconciliation rather than being erased or assigned invented closing prices.

**Persistence and visibility:** writes require a returned row acknowledgement, retain owner/run predicates, and raise sanitized errors. They run off the async event loop, serialize per colony, and are not automatically retried. The PostgREST client has a five-second transport timeout and no persisted/refreshed Auth session. This is a transport timeout, not a guaranteed total wall-clock deadline. Lifecycle diagnostics use the existing `vn_colonies.config.runtime` JSON field and preserve the original launch configuration. `state_persisted=false` honestly reports that a failure could not be saved; in-memory state then cannot be relied on to survive process restart. No schema migration was added or applied for these diagnostics.

The dashboard retains its last successful reads during outages and displays independent query/status errors with retry. Empty success remains distinct from a failed query. Persisted terminal states and safe failure/reconciliation diagnostics remain visible when the worker is unavailable; stored `running` status is not treated as current worker authority. Startup failures retain the configuration dialog and its settings. Known-field 422 messages are shown without reflecting arbitrary server messages, request values, or unknown field names.

**Market adapter:** the Jupiter price adapter validates the complete requested asset batch before updating its cache. HTTP rate limits/errors/redirects, timeouts, malformed responses, missing assets, and nonfinite/nonpositive prices fail explicitly; expired cache entries no longer become indefinite successful market observations. Configured Birdeye volume-request failures propagate instead of silently succeeding, and partial volume batches do not update the cache. Provider redirects and inherited HTTP proxies are disabled and raw provider exceptions are not logged. No automatic provider retry was added. Candle/event-time freshness, empty optional historical responses, absent optional Birdeye credentials, repeated candle volume, and signal warm-up semantics still require ENG-02/ENG-03/DATA work. This pass does not establish historical data quality or realistic execution costs.

**Dependencies and reproducibility:** [DEPENDENCY-REVIEW.md](DEPENDENCY-REVIEW.md) records the complete review. Next/config are pinned to 16.3.7, React/DOM to 19.2.8, and ESLint to 9.39.5 with compatible transitive fixes. Full/production npm audits report zero known vulnerabilities. The worker uses CPython 3.12.14, exact direct inputs, and runtime/dev hash locks with 49 packages each; clean installation, `pip check`, and both Python advisory scans pass. The isolated validation interpreter uses OpenSSL 3.5.8, avoiding the earlier system-Python LibreSSL warning without changing global Python. The documented ESLint/plugin and HTTPX2 test-client maintenance items remain open.

**Release gate:** Next.js says 16.3.7 does not contain the security fixes planned for September 30, expected in 16.3.8/15.5.27. Review the actual release and advisories, update to the reviewed patch, and retest before deployment. The current zero-advisory result does not close SEC-05.

**Verification:** the final frontend suite passes 35 tests; project-wide source/test lint passes with zero errors and 34 existing warnings. The seven earlier component-definition lint errors are fixed. TypeScript and an isolated production build using the default Turbopack bundler pass; an earlier webpack build also passed. Builds used a temporary source copy, project-local dependency copies, explicitly fake application credentials/`.invalid` endpoints, disabled telemetry, and no environment files. The real repository's `.next` output was preserved. Public build/dependency downloads are distinct from the offline application tests. The complete backend suite passes **107 tests** under the new Python lock, giving **142 passing offline tests** together with the frontend suite. `git diff --check` passes. Node native-TypeScript tests still emit their module-detection warning, and Starlette TestClient emits its documented HTTPX2 migration warning; neither was hidden or treated as a failed test.

To reproduce the full offline worker suite using the isolated environment created during this batch (temporary and not a permanent deployment environment):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 PYTHONPATH=services/vonneumann \
  /private/tmp/dashboard-sec05/worker/bin/python -m unittest discover \
  -s services/vonneumann/tests -t services/vonneumann
node --test tests/*.test.mjs
./node_modules/.bin/tsc --noEmit --incremental false
./node_modules/.bin/eslint src tests
```

For a durable fresh environment, follow the hashed-install instructions in DEPENDENCY-REVIEW.md. Do not use the old system Python for the new dependency lock. Do not run an ordinary local production build with real environment files merely to reproduce the isolated build evidence.

The missing remote `vn_probes.parent_ids` column still blocks a controlled real worker start. The new behavior makes that failure visible; it does not bypass the schema problem. Preview isolation, worker hosting, actual browser/auth/RLS verification, target-platform installation, database reconciliation, and the engine's funding/indicator/fitness/optimizer defects remain required backlog work. Same-colony snapshot/socket merge ordering is still UI-02. No claim is made that this batch makes the trading strategy profitable or ready for real funds.

## 9. GitHub review workflow

The user authorized committing, pushing a feature branch, opening a PR, and correcting the local origin URL. GitHub confirmed `TOOTRJ/TheDashboard` (repository `1141090963`) is private and the signed-in account has push access. Local and remote `main` both resolved to `254cdbab0958d5dc28b0f7c13ce8c8f5b64b6ccb` before branch creation. No GitHub Actions workflows were configured at that check.

The review branch is `codex/dashboard-security-reliability`. Existing application edits that the tested bundle depends on are preserved in a separate prerequisite commit. They are not presented as completed evolutionary-engine repairs: the funding, indicators, optimizer semantics, aggressive risk defaults, and other open engine tasks still require their listed acceptance tests. Historical migration edits, the unreviewed forward migration, `.claude/`, build output, Supabase temporary state, environment files, and credentials stay outside the PR.

The allowed Vercel project name/ID/team and linked GitHub repository ID were reverified read-only before publication. The branch has a narrowly scoped `git.deploymentEnabled` rule in `vercel.json` that disables automatic deployments for this exact branch, following [Vercel's Git configuration contract](https://vercel.com/docs/project-configuration/git-configuration). This allows code review while preview database isolation and release gates remain unresolved. It does not disable deployment of `main` or authorize merging, deployment, migration, credential changes, or trading. No Vercel project settings were mutated to create the guard.

## 10. ENG-01 funding and population continuity

The authorized continuation repairs local controller funding and updates the existing draft PR. It does not deploy, run a migration, access a real trading account, or change Vercel/Supabase configuration. GitHub repository identity `TOOTRJ/TheDashboard` / `1141090963`, canonical origin, and draft PR #1 on `codex/dashboard-security-reliability` were reverified. The exact-branch Vercel deployment guard remains in place, and the excluded local migration/configuration/build artifacts remain untouched.

**Reproduction and result:** actual PSO and CMA-ES each turned six $100 candidates into an empty population after six replacements despite retaining the entire $600 in reserve. Every child now receives the configured `seed_capital`; the old `capital_split` constructor argument remains accepted for compatibility but no longer controls candidate budgets. Parent gains/losses flow to reserve, so this does not fabricate money or promise unlimited replacement after real losses.

Initial seeding and mandatory replacement preflight the complete batch before applying controller mutations. The checks cover candidate/lineage validity, unique registered retirement IDs, valid parent states, population capacity, positive finite liquidation prices, cash validity, and the full series of funding debits. Retirement uses the same prices and liquidation arithmetic as preflight. Compensated cashflow sums avoid cumulative rounding drift; any permitted adjustment is bounded to eight ULPs and at most $0.000000001. An economically unaffordable batch fails without retiring its parents or silently dropping/underfunding children. Optional diversity checks affordable slots before generating new genomes.

A mandatory refusal stops the colony with a specific safe funding/capacity/plan error. `evolve()` may already have advanced optimizer bookkeeping, so refused plans are not automatically retried. Self-reproducing probes may already have closed positions and persisted reproduction intent; refusal retains that parent in `REPRODUCING` for reconciliation. A persistence error after work begins preserves partial child/parent records and cash ownership without automatic rollback or retry. Status includes the value of every still-registered account, including a `DEAD` account whose removal was interrupted. Duplicate death/reproduction handling does not reclaim the same capital twice. Simultaneous deaths pool recoverable funds before extinction is reported, and an empty colony cannot continue silently.

**Scope limits:** this is a fixed evaluation-budget repair. Capacity exhaustion from GA population growth is explicit and terminal until a bounded strategy policy is implemented under ENG-06/ENG-07. CMA cohort interruption/history, market-data timeframes, trade arithmetic outside validated controller retirement, fitness, fixed-gene semantics, execution costs, durable terminal records, and restart reconciliation remain open. The test fixtures restrict optimizer dimensions and disable optional diversity when testing zero-return continuity; they do not establish performance or correctness of a trading strategy. The two-gene baseline remains downstream of those engine/data/risk tasks.

**Verification:** 28 new offline funding tests cover four 60-cycle runs (real PSO and CMA-ES with six $100 candidates, PSO with six $33.33 candidates, and PSO with 28 $100,000.01 candidates), actual GA partial replacement, reserve-only and self-reproduction births, profits/losses, optional diversity, malformed plans/prices/ledgers, capacity/funding refusal, simultaneous death/extinction, and persistence interruption. Two additional lifecycle regressions prove funding errors reach persisted/published terminal status without automatic retry and sanitize unknown error codes. The existing frontend suite now also checks all four user-facing funding/population messages. The complete suite passes **137 Python tests and 35 Node tests (172 total)**. TypeScript passes; source/test lint reports zero errors and 34 existing warnings; `git diff --check` passes. The prior isolated production build remains the build evidence for the security/reliability batch; it was not repeated for this backend repair and documentation/error-message update. No cloud application I/O was used by the regression tests.

## 11. Main-branch release authorization and dependency follow-up

The user explicitly authorized pushing, merging to `main`, and production deployment, then requested a focused dependency follow-up before further engine work. PR #1 was merged as `80391b4763ae2479c12f524875f5eae25b5ecfe6`. This supersedes the earlier draft-only publication restriction; the exact project/account boundaries and prohibition on live trading remain in force. No database migration or credential rotation is part of this release.

Before the merge, read-only metadata again matched Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` / `team_8iNNxiNjrOseD4gdSCHkQEzF`, production branch `main`, linked GitHub repository `1141090963`; Supabase again matched `The Dashboard` / `fxpxsciltakyypunglzr` / `cqfnnaunmupdyobkyqfo` and reported `ACTIVE_HEALTHY`. The dedicated CLI profile and explicit target IDs were used throughout.

The public production alias resolved to the older READY deployment `dpl_w6f9JzQ59syDqEExozGaLcGXHKnE` before this release. The project's production target metadata instead named a failed later attempt, so that failed target is not a verified rollback candidate. The READY deployment is the recorded rollback reference. No automatic deployment or GitHub build check appeared immediately after PR #1 merged; publication is not reported as successful deployment solely because the merge succeeded. The combined release was subsequently verified as recorded below; the Git integration repair remains open under RELEASE-01.

The dependency follow-up updates the compatible JavaScript graph, declares the existing Node 24 production major, fixes the required chart typing, and ensures Recharts uses React-compatible fragment detection. Next/config remain at latest published 16.3.7 because the announced 16.3.8/15.5.27 security patches were still absent from npm. Their availability/advisory review remains SEC-05; user approval does not establish that those unknown fixes are present. See DEPENDENCY-REVIEW.md for exact decisions and evidence. Local validation: 36 Node tests, TypeScript, isolated default-Turbopack production build, zero-error lint with 33 existing warnings, and zero-known-vulnerability full/production npm audits. No authenticated cloud session, colony start, database write, or trading action was used for these tests.

**Verified production release (2026-09-30 UTC; September 29 America/Denver):** [PR #2](https://github.com/TOOTRJ/TheDashboard/pull/2) merged as `bf38baedddf125a60966d258806660593d6e013d`. Neither merge triggered a deployment; Vercel’s explicit Git-source API rejected the verified repository with “The provided GitHub repository can't be found.” Project metadata still reports the former repository owner, despite matching immutable repository ID. No shared GitHub installation or account permission was changed. A clean `git archive` of the exact merged commit was deployed through the dedicated profile, pinned to the allowed project and team; it excluded environment files, untracked drafts, and local build output.

The deployment API independently confirms `dpl_9djgN8sVgzkKmda9gYPBL3T3oWow`, project `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`, team `team_8iNNxiNjrOseD4gdSCHkQEzF`, target `production`, state `READY`, Node `24.x`, and `releaseCommit=bf38baedddf125a60966d258806660593d6e013d`. Inspection of [the public production alias](https://the-dashboard-chi.vercel.app) resolves that same deployment. [Deployment details](https://vercel.com/orderoftheredjester/the-dashboard/9djgN8sVgzkKmda9gYPBL3T3oWow).

Read-only production smoke checks: `/login` returned 200; `/` returned 307 to `/login`; `/api/v1/test?limit=0` returned 401 without a credential and 200/success/zero rows with the configured API key. Credential-bearing redirects were disabled. These checks verify the served routes and the database read path; they do not establish an authenticated browser session, chart rendering, worker connectivity, RLS isolation, or trading correctness. No POST, migration, colony launch, or trade was performed. The earlier READY deployment remains the recorded rollback candidate. RELEASE-01 tracks automatic deployment repair; SEC-05 remains open because the announced security patches were not published at the release check.

ENG-02 was paused for the requested dependency PR. Its untracked test draft remains local and is excluded; it requires its corresponding source implementation before it can be run. The worker hosting/schema, source-price freshness, optimizer correctness, and realistic-execution tasks remain open independently of dashboard deployment.

## 12. ENG-02 arithmetic and bounded failure isolation

The authorized continuation implements the arithmetic and failure-reporting portion of ENG-02. The exact GitHub repository and both cloud project names/IDs/owners were reverified; Supabase reported ACTIVE_HEALTHY. This implementation uses offline tests and fake feeds. No database migration, real colony start, live signing, provider trade, credential change, or shared account/profile modification was used. Merge/deployment evidence for this continuation is recorded in its pull request; section 11 retains the verified prior dashboard deployment and rollback baseline. The Python worker is not deployed by Vercel's Next.js build.

- Shared validation rejects missing, boolean, string, negative, nonfinite, and unrepresentable inputs before observations or simulated ledger changes. Price must be positive; volume can be zero. A missing exit is invalid; an explicitly recorded zero terminal loss realizes a -100% return. Ordinary zero quotes cannot trigger a refund or liquidation.
- RSI defines flat windows as neutral 50, no losses as 100, and no gains as 0. Scaled sums avoid the old epsilon and sum overflow. The existing rolling-window averaging is retained, not replaced by Wilder smoothing. Backtrader's [safe RSI policy](https://github.com/mementum/backtrader/blob/master/backtrader/indicators/rsi.py) supports explicit zero-denominator outcomes; this does not establish numerical parity with its default smoothed RSI. Completed candles, EMA warmup, and independent indicator fixtures remain ENG-03 work.
- Close proceeds use scaled direct position valuation instead of adding principal to a rounded loss. This preserves small positive remaining value when a return rounds to -100%, and avoids intermediate ratio underflow when the final value is representable. An unrepresentable positive final value fails before mutation. Lifecycle and scheduled replacement plans validate all marks, cumulative cash, and projected summaries before closing any parent.
- Genesis excludes invalid or missing current observations and replaces its latest-price cache; a prior mark cannot substitute for a missing current quote. Every eligible probe gets a risk pass before signal/entry decisions. A step failure carries completed events for persistence, then the supervisor stops execution with a fixed safe error. A valid asset can still close when another asset or probe fails. Missing quotes cannot justify fabricated fills.
- A malformed ledger cannot prevent the manager from entering a failed lifecycle state. JSON-safe status uses null monetary values and `valuation_available=false` when current value is unknown. The dashboard shows Unavailable, preserves the diagnostic in the existing runtime JSON, and labels valid worker totals as last reported. No schema addition is required.

**Verification:** the complete worker suite passes **188 tests**, including 51 new arithmetic/isolation/lifecycle regressions and the existing 28 funding checks. All **38 Node tests** pass. Full TypeScript and an isolated default-Turbopack production build pass; broad source/test lint reports zero errors and 33 existing warnings. Worker tests use the isolated CPython 3.12 environment with network/database access denied; frontend tests/build use isolated Node 24.21.0, fake configuration, and no real environment files. The build preserves the repository's existing `.next` output. Independent code review covered cross-probe risk ordering, partial event preservation, unavailable valuation, replacement preflight, and numeric overflow/underflow. Both pre-existing migration files retain their prior hashes.

**Limits kept open:** this is a bounded risk pass followed by terminal failure, not a continuing quarantine system. If event persistence fails partway through, in-memory accounts/trades remain available for reconciliation, but no durable outbox, automatic replay, or cross-table transaction guarantee is added. The existing historical drawdown, fitness, circuit-breaker, optimizer, and realistic-fill defects remain their separately ordered engine tasks.

**Freshness research:** Jupiter [documents `blockId` as the price-recency signal](https://developers.jup.ag/docs/price). The adapter currently drops it and timestamps HTTP receipt; numeric timestamp validation cannot detect an old source observation. Birdeye volume/history timestamps and a shared replay clock also require a defined source-data contract. ENG-02 remains open for that acceptance work through DATA-01/ENG-03/RES-03. Do not infer age from token creation time, HTTP success, or an assumed constant block duration.

## 13. Verified worker schema migration — 2026-09-30

The user explicitly authorized applying migrations after confirming the exact Supabase project. At `2026-09-30T06:48:47Z`, provider metadata returned **The Dashboard**, ref **`fxpxsciltakyypunglzr`**, organization **`cqfnnaunmupdyobkyqfo`**, status **ACTIVE_HEALTHY**. This repository's project-ref and cached connection username independently matched the same ref. The differently scoped Supabase connector was not used. Shared CLI authentication and the other agent's project were untouched.

The ten remote history entries matched the ten tracked versions. Catalog inspection found two specific gaps: no `vn_probes.parent_ids` and a trade CHECK restricted to five reasons. The enabled colony trigger already resolved to `extensions.moddatetime`; the four UUID run IDs and generation uniqueness were already correct. The dry run named exactly the two reviewed files, which were then applied successfully:

- `20260418120000_vonneumann_parent_ids.sql`: adopted the existing draft's JSONB column/default and GIN index, adding only timeout statements before application. Existing `parent_id` and embedded genome ancestry were preserved, with no historical backfill.
- `20260930010000_vonneumann_trade_exit_reasons.sql`: expanded the existing check to include `EVOLUTION` and `TERMINAL_LOSS`, retaining five prior values and NULL. The dashboard's `TradeExitReason` union now matches. The old applied colony-migration edit remains local and was not replayed or included.

**Verified outcome:** the history now contains all 12 versions; a subsequent dry run has no pending migrations. Catalog comparison confirms exactly the new JSONB NOT NULL/default column, valid/ready GIN index, and validated seven-reason CHECK. Other existing column, constraint, index, policy, RLS, extension, and trigger definitions are unchanged; actual update-trigger function bindings also match. All 18 policies and five RLS flags are preserved. Definition rendering was compared with consistent PostgreSQL pretty-print settings to avoid treating formatting as schema drift.

[The database contract script](supabase/tests/worker_schema.sql) passed against temporary copies of the deployed definitions inside an explicit transaction ending in ROLLBACK. It accepts all seven exit reasons and NULL, rejects an unknown reason, verifies ancestry default/nullability/two-parent round-trip, permits separate runs/owners at the same generation, rejects duplicate owner/run/generation, and executes the repository's exact upsert conflict target. It returns only `worker_schema_contracts_ok`. It writes no public/auth records and does not claim to test copied foreign keys, RLS, or the service/UI path. A privileged `select=parent_ids&limit=0` PostgREST read returned HTTP 200 and zero rows, confirming API schema-cache visibility without reading application data. TypeScript, all 38 frontend tests, focused type-file lint, and diff whitespace checks pass. The prior 188-worker-test run remains the worker evidence; this migration/type-only batch did not rerun that unchanged code or rebuild the dashboard.

**Execution caveat:** CLI 2.84.2 emitted `SET LOCAL can only be used in transaction blocks` for the timeout statements. Both migrations and postchecks succeeded, but effective timeout enforcement was not verified and must not be claimed. The upstream executor describes an implicit transactional batch, while the warning demonstrates that relying on explicit-transaction settings in this path needs further validation. The single-statement CHECK replacement remains atomic as an ALTER TABLE operation. Preserve the exact applied files/history; investigate and prove the runner's transaction and timeout behavior in an isolated environment before future DDL. The earlier commentary that timeouts were definitely not enforced was too strong; the supported conclusion is that enforcement was unverified.

[The migration plan](supabase/MIGRATION-PLAN.md) records preflight, application, verification, and rollback. Keep these backward-compatible schema additions if reverting an application release. Do not drop ancestry or reimpose a narrower CHECK after new records use it; prefer a reviewed forward repair. No colony, worker process, funding, signing, swap, live trade, RLS/grant change, credential rotation, Vercel setting change, or other-project edit occurred. DB-01's full event round-trip and DB-04's unrelated schema provenance remain open.

For the prior ENG-02 dashboard release, PR #4 merged as `7ecab3e68ef391debf945b5ce8e421f85370ddc9`; verified production deployment is `dpl_FkBcnvsTfsDyQmhQcP6qRKFxTne3`, [deployment details](https://vercel.com/orderoftheredjester/the-dashboard/FkBcnvsTfsDyQmhQcP6qRKFxTne3). The migration batch changes Supabase directly; it does not require a new frontend build for its SQL effects. The TypeScript-only union change has no emitted JavaScript behavior. No new Vercel deployment was initiated for this batch.

## 14. Synthetic market clock and next data contract — 2026-09-30

The next engine repair addresses a prerequisite discovered while investigating ENG-03. Global optimizer/name randomness previously changed simulated prices, and wall-clock timestamps made playback speed change recorded experiment dates. `SimulationFeed` now owns deterministic per-asset RNG streams and a modeled clock. Every nonempty batch advances all eight supported assets exactly once, even when candidates request different subsets or orders. The complete price/volume/RNG/time frame is validated before commit; invalid data cannot partially advance the feed.

**Model contract:** defaults are seed `0`, synthetic start `2024-01-01T00:00:00Z`, and 60 modeled seconds per frame. The first observation is one step after the start. The constructor supports explicit seed/start/step values; this batch does not add configuration-dialog controls for them. Prices use positive geometric log returns with parameters defined per modeled step. Overflow, underflow to zero, invalid variance/volume, and an unrepresentable or non-advancing clock fail explicitly. A log-domain fallback preserves representable results when exponential factors overflow, underflow, or lose relative precision as subnormals. These are uncalibrated generated prices and volumes, not historical OHLCV, liquidity, or a realism claim. The historical date is an artificial anchor, not a claim about trading in 2024.

**Event and persistence contract:** controller-created probes, trade opens/closes, lifecycle events, generation boundaries, and fitness snapshots use modeled time in simulations. Persistence preserves the event's validated, timezone-aware UTC timestamp instead of substituting database/write time. Real service start/uptime remain wall/monotonic time; changing playback speed or reading status does not advance market time. Paper events retain wall time; that does not establish the freshness of the underlying price. Runtime JSON saves `clock_basis`, `market_time`, `market_elapsed_secs`, and `simulation_spec` (model version, seed as an exact decimal string, start, step, drift, volatility, volume noise). The dashboard explains the synthetic clock for both live status and saved history. Legacy records without explicit metadata are not relabeled. Existing JSON storage suffices; no migration or historical-record rewrite is required.

**Verification:** all **225 Python tests and 40 Node tests pass**. The 37 new clock tests include the real controller, probe ledger, and event persister using a fake database; configured runs at 100 ms and 5,000 ms playback produce matching prices, trade fields, and timestamps despite additional global random draws. Fixed genomes and entry signals deliberately isolate timing from optimizer behavior. Other cases cover requested-asset order/subsets/duplicates, empty batches, invalid-frame rollback including RNG Gaussian caches, UTC normalization, event/payload timestamp precedence, clock precision, lifecycle order, and independent 80-digit Decimal checks for extreme prices. TypeScript, an isolated Node 24 production build, and diff whitespace checks pass. Broad source/test lint has zero errors and 33 existing warnings. Independent review found and verified fixes for subnormal-factor precision, paper reproduction event ordering, and the saved-history label gap. Tests/build used fake settings and no cloud writes; the repository's existing build output was preserved.

**Limits and next implementation order:** this is the clock/RNG prerequisite only. Tick-count timeframes, shared candle history, EMA seeding/state, source freshness, realistic execution costs, optimizer reproducibility, and resumable dataset/ledger manifests remain open. Arbitrary external feeds that advertise a clock must maintain the same valid-clock contract; a feed without that capability retains wall event time. Runtime metadata is not a checkpoint. The Python worker still has no configured deployment; a Next.js release publishes dashboard changes only. Keep the backward-compatible runtime metadata if reverting the frontend. Reverting the worker to wall-time semantics requires explicitly distinguishing new runs from records already labeled with synthetic time.

The following primary-source research guides the next data repair; it is not implemented by this batch:

1. **Separate current quotes from completed indicator candles.** Jupiter's [token-price guide](https://developers.jup.ag/docs/guides/how-to-get-token-price) describes USD prices and source `blockId`; `createdAt` is token creation time. Preserve source slots and separate receipt wall/monotonic time. Bounded, deduplicated [Solana `getBlockTime`](https://solana.com/docs/rpc/http/getblocktime) calls can supply estimated source timestamps and may return null. [Current slot context](https://solana.com/docs/rpc/http/getslot) is useful evidence, but does not prove quote finality. Unknown source age must not become fresh solely because HTTP succeeded. Cached observations need age rechecking; repeated slots alone do not prove identical quotes, since multiple trades can occur in a slot. Initial 30-second maximum age, 2-second future tolerance, and 5-second HTTP deadline are candidate project policies to validate, not provider SLAs. Explicitly resolve the current USD-price/USDC-ledger approximation.
2. **Normalize validated source candles and aggregate arbitrary supported gene timeframes.** Birdeye's official [Solana chart guide](https://birdeye.so/data-api/blog/detail/solana-tradingview-chart-api-birdeye-data) describes V3 OHLCV with `unix_time`, OHLC, `v`, and `v_usd`; the [changelog](https://birdeye.so/data-api/changelog) distinguishes token and USD volume. Its [sub-minute interval announcement](https://birdeye.so/data-api/blog/detail/introducing-sub-minute-intervals-in-birdeye-data-services-ohlcv-v3-apis) describes unpadded bars, so a missing minute must not be silently fabricated. Its [price-alert guide](https://birdeye.so/data-api/blog/detail/token-price-alert-monitor-solana-birdeye-data) warns that the latest bar can still be forming. Build canonical per-asset one-minute history and UTC-aligned integer 5–60-minute aggregation; the current unsupported-timeframe fallback to 15 minutes needs replacement. Require complete constituent minutes, positive bounded OHLC, explicit volume units, and bar-end time no later than the accepted clock minus a reviewed completion margin. A two-second margin is a candidate policy, not a guarantee of immutable bars. Define duplicate, out-of-order, and revision handling explicitly. Some reference links from the provider guides returned 404 during research; verify actual entitled API responses, limits, and fixtures before committing an adapter contract.
3. **Share indicator history and preserve risk ordering.** Keep fresh quote-based valuation/risk checks available while candle history warms up. Volume filtering needs 20 prior observations plus the current completed candle; missing or zero baseline volume must not imply an automatic pass. Seed EMA from the specified SMA, then preserve recursive state consistently across original probes, children, and timeframe changes. Repeatedly reseeding from a truncated buffer can give different values to candidates observing the same market. Warm-up must not create retroactive trades. A completed-bar signal becomes fill-eligible only at a subsequent execution observation under FILL-01.
4. **Research further before strategy comparison.** Validate real source latency/slot-time coverage, sparse-bar policies and revisions, volume/currency conversions, plan entitlements/quotas/costs, survivorship bias, dataset hashes, calibration, and cross-runtime replay tolerance. Independently seed the optimizer and persist a full experiment/checkpoint manifest before claiming whole-run reproducibility. Keep RES-01/RES-02 evaluation and execution-cost gates before the two-gene baseline.

**Remote boundary and release:** read-only metadata again matched GitHub `TOOTRJ/TheDashboard` / `1141090963`, Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` / `team_8iNNxiNjrOseD4gdSCHkQEzF`, and Supabase `The Dashboard` / `fxpxsciltakyypunglzr` / `cqfnnaunmupdyobkyqfo` / ACTIVE_HEALTHY. The production alias still resolved to READY deployment `dpl_FkBcnvsTfsDyQmhQcP6qRKFxTne3`, which is the rollback baseline. Merge/deployment evidence for this batch is recorded in its pull request. No database mutation, live worker/colony start, credentials/shared-profile change, signing, swap, funding, or other-project edit is part of this repair.

## 15. Paper quote source freshness and RPC setup — 2026-09-30

DATA-01A implements estimated source-block age checks for current paper quotes. It builds on the deterministic simulation clock but leaves completed candles, volume semantics, shared indicator history, USD/USDC conversion, realistic fills, and optimizer correctness open. No database schema or record change, worker/colony start, wallet operation, credential rotation, or other-project edit was used to implement or test it.

**Evidence from an actual provider response:** a bounded read-only check used the existing Jupiter and Helius credentials, disabled credential-bearing redirects, and verified Helius's mainnet genesis hash. Jupiter returned HTTP 200 and all eight requested mints; six unique slot lookups resolved their source times. Ages at HTTP receipt ranged from 2.507 seconds to **112.507 seconds for PYTH**, with ORCA at 23.507 seconds. The old receipt-time implementation would have accepted all as newly received. This is one observed sample, not a latency distribution or uptime guarantee. [The sanitized public fixture](services/vonneumann/tests/fixtures/jupiter-source-times-20260930.json) contains only public price/slot/time observations; it has no keys, RPC URL, account metadata, or raw private response. Offline replay rejects PYTH, retains seven fresh siblings for risk, and does not commit a partial quote cache.

**Implemented contract:** `MarketTick.timestamp` is estimated source block time for paper quotes. Immutable quote evidence separately records source slot, actual receipt UTC, receipt monotonic time, provider `jupiter-price-v3`, currency `USD`, and an effective age floor. The versioned local policy accepts source age at most 30 seconds and future-clock allowance at most 2 seconds. Age is conservatively checked against both current wall time and monotonic elapsed time. Carried age floors survive subsequent HTTP receipts and higher slots whose estimated timestamps have not advanced; fetching an old source again cannot reset age after a wall-clock rollback. A genuinely newer source can replace expired evidence. Same-slot price changes are allowed, lower accepted slots are rejected, and a changed timestamp for an unchanged slot is an explicit invalid-evidence outcome. The watermark is per run, not durable reconciliation across restarts.

Jupiter and RPC headers are separate, HTTP redirects are disabled, and inherited proxy settings are not used. The adapter validates JSON-RPC version, response ID, result/error shape, source-slot integer type, and timestamp values. It checks the complete mainnet genesis hash once per HTTP session and clears cached block evidence when that session changes. Each Jupiter-plus-RPC refresh has a five-second overall deadline, at most eight distinct source slots and four concurrent RPC lookups. Successful block-time evidence is bounded to 256 entries and 30 monotonic seconds; quote cache TTL remains 0.8 seconds and every hit rechecks source age. A small deadline margin permits cancelling/draining unfinished lookups and validating completed siblings. Explicit cancellation propagates without committing a partial quote batch. Quote cache/order state commits only on complete success; no automatic retry or fallback provider is added.

**Controller behavior:** paper mode independently validates the adapter's evidence, retains it with the marks, and carries its own accepted-source age anchor. A partial feed error supplies only newly validated siblings for a final risk pass. A stale/missing asset cannot close at an old cached price, while a fresh sibling's stop can complete and persist. Signals and evolution then stop. Quotes are checked again before subsequent probe decisions, lifespan liquidation, each planned retirement, and each replacement funding step because awaited database writes/broadcasts can outlast quote validity. An expired later step retains earlier completed events and account ownership; this is not a transaction rollback. Paused/failed status reports open-position valuation as unavailable when marks expire; cash-only value remains available. Paper event timestamps remain actual wall time, distinct from the older quote source time. Runtime JSON records `quote_policy`; fixed UI messages distinguish stale, invalid/unknown source evidence, and missing/wrong-network RPC configuration without exposing secrets.

**Required worker setup:** this batch introduces a deliberately explicit connection setting and does not edit any environment file or remote settings. When configuring the worker:

1. Obtain the HTTPS **mainnet** RPC endpoint from the intended provider project. The existing Helius key passed the limited method checks above; no new account or purchase is implied. An endpoint may embed its key in the path or query string and must be treated as a secret.
2. Set `VN_SOLANA_RPC_URL` in **this worker's private environment** alongside its existing `JUP_API_KEY`. For local work, use only this repository's ignored worker environment file and the documented worker launch directory; for hosting, use only the selected worker service's secret store. Do not alter shared shell startup files or another agent's project. Do not put the setting in `NEXT_PUBLIC_*`, send it to the browser, or add it to the Vercel frontend merely to satisfy worker setup.
3. Keep HTTPS enabled and select Solana mainnet. Startup/feed validation checks `getGenesisHash` against `5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d`. No public RPC fallback is selected automatically. Wrong/missing configuration becomes an explicit failed colony state.
4. Before sustained paper use, verify the actual plan's quotas and coordinate them with every other application sharing that provider organization. Selecting multiple colonies at one-second pacing is not evidence of sufficient quota. Do not change shared provider credentials or permissions to fix a project-local setting.

Simulation does not need the RPC URL. The Python worker remains undeployed; Vercel's Next.js release only updates dashboard failure explanations. The new policy can legitimately reject startup or stop a paper run containing a stale asset such as the sampled PYTH observation. Retain that failure instead of widening the limit or substituting receipt time. Worker readiness also requires the unresolved candle/volume and lifecycle acceptance work; accepting a quote is not permission to trade live.

**Research basis and remaining work:** Jupiter's [token-price guide](https://developers.jup.ag/docs/guides/how-to-get-token-price) identifies `blockId` as price source and returns `usdPrice`; `createdAt` is token creation. A reference mark is not an amount-specific executable quote. [Solana `getBlockTime`](https://solana.com/docs/rpc/http/getblocktime) provides estimated Unix block time with no commitment parameter; the [docs-linked Agave implementation](https://github.com/anza-xyz/agave/blob/v3.1.8/rpc/src/rpc.rs#L1481) can consult non-rooted banks. Neither a resolved timestamp nor a [current-slot comparison](https://solana.com/docs/rpc/http/getslot) proves a Jupiter swap's ancestry/finality. The full genesis constant is defined by the [official Anza SDK](https://raw.githubusercontent.com/anza-xyz/solana-sdk/master/cluster-type/src/lib.rs); a truncated wallet chain identifier is insufficient. Genesis pinning prevents accidental cluster mismatch, not a malicious RPC.

Jupiter's [current rate-limit documentation](https://developers.jup.ag/docs/portal/rate-limits) describes a shared organization quota across keys/teams and a 60-second sliding window, with Free listed at one request per second. Helius's [rate-limit guidance](https://www.helius.dev/docs/billing/rate-limits) and [RPC reference](https://www.helius.dev/docs/api-reference/rpc/http/llms.txt) distinguish batch constraints and per-method credits; `getBlockTime` is currently listed at 10 credits. Research actual continuous-operation costs, shared multi-colony scheduling, near-tip time availability, clock drift, fork/revision policy, and source-age distributions before production operation. The adapter currently retains the existing USD-price/USDC-ledger approximation, explicitly records USD provenance, and does not fix it by relabeling data. Proper conversion requires a separately fresh USDC/USD observation and a reviewed fill/accounting model. Repeated quote samples and cached Birdeye volume still do not constitute completed candles.

**Verification:** all **281 Python tests and 40 Node tests pass**, along with TypeScript, an isolated Node 24 production build, and diff whitespace checks. Lint has zero errors and 33 existing warnings. The 56 additional worker regressions cover adapter/RPC contracts, source-age policy, partial risk, lifecycle diagnostics, post-await mutation boundaries, cancellation, and the sanitized real sample. Independent review found no additional blocker. Tests deny network access. Separately, after the eight-asset sampling above, one bounded call through the actual new `aiohttp` adapter accepted SOL with 2.651-second estimated source age, using one Jupiter request and two read-only RPC calls (genesis and block time), then closed its session. It neither started a worker/colony nor wrote records/settings. These two deliberate provider checks establish limited method/contract compatibility, not continuous readiness.

**Release boundary:** publication/deployment evidence is recorded in this batch's pull request. Exact GitHub repository identity, Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` / `team_8iNNxiNjrOseD4gdSCHkQEzF`, and Supabase `The Dashboard` / `fxpxsciltakyypunglzr` / `cqfnnaunmupdyobkyqfo` / ACTIVE_HEALTHY were reverified. The pre-release alias served READY deployment `dpl_EZw2c5GLEPdMtYrSP2CRNAcD9zPj`, retained as rollback baseline. No additional migration is needed; runtime policy metadata is backward-compatible. A worker rollback would remove freshness protections and must not be treated as a safe way to bypass a stopped paper run.

## 16. Completed candles, shared indicators, and causal signals — 2026-09-30

This repair replaces poll-count signal timing and the parent-buffer inheritance path. It requires no schema change, writes no database records, changes no credential or project settings, and starts no worker/colony. Python remains unhosted; a Vercel release publishes the dashboard's new candle failure explanations, not the worker.

**Verified provider contract:** the existing private Birdeye key returned HTTP 200 from `GET /defi/v3/ohlcv` for a small SOL window. The [sanitized public fixture](services/vonneumann/tests/fixtures/birdeye-v3-candles-20260930.json) includes ten completed one-minute records and a still-forming eleventh record. V3 uses `unix_time`, explicit mint/interval/currency fields, token volume `v`, and USD volume `v_usd`. The adapter requests `type=1m`, `mode=range`, `currency=usd`, `chart_type=price`, `ui_amount_mode=raw`, and `padding=false`; it does not mix the deprecated camel-case schema with V3. This sample establishes observed key access/schema, not continuous readiness or all-asset coverage.

**Candle policy:** only intervals ending at or before `floor((current_time - 5 seconds) / 60) * 60` enter paper history. Five seconds is an explicit local margin, not a Birdeye finality guarantee. An initial request covers 3,660 minutes, enough for sixty complete hourly bars when the source returns continuous data, within the provider's 5,000-record limit. Subsequent calls use a two-minute overlap; initially short token history bounds the overlap at its first accepted minute. Each request has a five-second deadline and each serialized batch a sixty-second deadline; the worker's existing startup timeout remains thirty seconds, so an overly slow warmup fails startup. The adapter does not raise that deadline or silently reduce history. Requests use a separate session, disable redirects/inherited proxies, and never log keys/private provider exceptions. One-second request spacing is local pacing, not enforcement of an account's shared quota.

The canonical store strictly validates finite positive OHLC, OHLC relationships, nonnegative volume, aligned timestamps, source/currency/volume-unit identity, and completion. It sorts incoming batches, makes identical overlaps idempotent, rejects conflicting completed revisions, and atomically rejects gaps or malformed observations. Forming endpoint records are validated then excluded by the adapter. Empty/missing trailing history is unavailable; leading short history can leave indicators warming. Missing minutes are never padded or labeled zero-volume. The store retains 4,096 minutes for overlap checking. Revisions older than the fetched overlap are not proactively discovered and require dataset/reconciliation research.

**Shared aggregation and indicators:** every configured asset has UTC Unix-epoch-anchored series for integer timeframes 1–60 (the current UI/genome domain is 5–60), including seven-minute buckets across hour/day boundaries. Complete buckets use first open, maximum high, minimum low, final close, and each minute's volume once; a leading partial bucket is ignored. EMA periods 2–60 share a single run history, seed from the first period's SMA, and update recursively even after raw history is trimmed. Sixty-four closes support the existing rolling RSI definition, and 21 volumes support current interval versus twenty prior intervals. Entries require valid RSI/EMAs and a positive prior-volume baseline; missing or all-zero volume cannot disable that filter. The EMA entry rule remains a trend comparison (`fast > slow`); the separate two-gene baseline's true crossover rule is still future work.

**Quote, signal, and execution order:** fresh quotes update dedicated marks for every valuation, risk, close, and lifecycle path. Eligible stop/take-profit checks and their persistence precede candle retrieval, so a candle outage cannot suppress an already valid stop. Quotes are revalidated after awaited history/persistence before decisions. New completed bars generate per-asset intents; an intent needs a quote source time strictly after the candle end and a receipt after actual signal availability. Paper uses monotonic receipt/availability boundaries; simulation uses modeled time. A cache hit received before signal availability cannot fill it. Intents expire after one timeframe, with exact expiry eligible for the next one-minute synthetic frame. Prior eligible intents execute before the next bar supersedes them. Risk closures cancel obsolete exits, exits retain their original trade identity, and retirement clears pending decisions. Terminal drawdown now takes precedence over reproduction and queued entries after risk checks. This prevents new exposure immediately before death, but does not complete circuit-breaker/recovery work.

Startup warms history before attaching decision cursors; child probes attach to their own asset/timeframe's current shared state. Neither startup, child birth, duplicate polls, nor multi-bar catchup can replay prior signals into today's quote. The initial simulation frame is ingested once; retrieving its candles does not advance the market. Synthetic OHLC is explicitly the two step endpoints, with synthetic base-token volume, and controller candle support requires aligned sixty-second steps. This provides no real intraminute extrema or calibrated liquidity.

**Validation:** all 354 offline Python tests and 40 Node tests pass. The new suites cover aggregation/completion/gaps/revisions, atomic failure, EMA hand calculations and high-precision boundaries, history trimming and child state, volume semantics, live-provider fixture replay, stop protection through candle failure, delayed quote causality, event preservation, and terminal lifecycle precedence. A real-indicator 500-frame controller replay using valid five-minute strategy settings produces identical bars, signals, and trade events at 100 ms and 5,000 ms configured playback, despite unrelated global RNG draws. TypeScript passes; lint has zero errors and the same 33 existing warnings. An isolated Node 24 production build also passes. A separate single-request live adapter check accepted 3,660 continuous SOL minutes, built sixty complete hourly candles, and seeded EMA 60, then closed the session. It started no worker and wrote no remote records. This validates the observed SOL history path only; release results are recorded with the pull request.

**Required setup and limitations:** paper mode now requires this worker's private `BIRDEYE_API_KEY` alongside `JUP_API_KEY` and `VN_SOLANA_RPC_URL`; simulation needs no provider keys. Keep these in the intended worker's environment, never in `NEXT_PUBLIC_*` or shared shell configuration. A sparse asset or provider revision may legitimately prevent startup/stop a run; do not bypass that outcome by padding bars or widening source-age limits. No live execution has been enabled. USD prices remain an approximation in the existing USDC ledger. Fees, spread/slippage, impact, execution rejection/latency, durable restart/replay and dataset manifests, optimizer cohort correctness, and research benchmarking remain open. Reproduction/lifespan schedules are still quote-tick based and can advance during indicator warmup, so early generations are not comparable experiments even though later children now share warmed indicators.

**Research follow-up:** use the [current V3 reference](https://data.birdeye.so/docs/data-api/price-ohlcv/get-defi-v3-ohlcv), [Birdeye's volume/schema changelog](https://birdeye.so/data-api/changelog), [completed-candle guidance](https://birdeye.so/data-api/blog/detail/token-price-alert-monitor-solana-birdeye-data), and [shared rate-limit guidance](https://data.birdeye.so/docs/guides/api-access/rate-limiting). Deeply verify actual V3 entitlements/compute-unit costs, completion lag and revision distributions, sparse-asset gaps/recovery, scaled-token handling, immutable datasets/licensing, and shared quotas across other applications. The V3 docs contradict themselves about the `outlier` flag; leave it unspecified pending provider clarification and do not claim unfiltered historical data. Research evaluation-ready scheduling before enabling optimizer comparisons or adding genes.

**Release boundary:** allowlisted targets are GitHub `TOOTRJ/TheDashboard` / `1141090963`, Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` / `team_8iNNxiNjrOseD4gdSCHkQEzF`, and Supabase `The Dashboard` / `fxpxsciltakyypunglzr` / `cqfnnaunmupdyobkyqfo` ; identity must be verified before each corresponding remote write. GitHub and Supabase metadata still match. Earlier Vercel metadata matched, but a later publication check found no saved credentials in the dedicated Dashboard profile and entered a login flow; that attempt was stopped. Deployment awaits deliberate sign-in and fresh identity verification, without using or changing the shared default profile. The preceding READY production deployment `dpl_2YV6ug8y19NSu6pgrJT5po6GKdqJ` at merged commit `612904171c38e0e1c86a176ff448b3d49da6937a` is the rollback baseline. Preserve other projects, the dedicated CLI profile boundary, and all pre-existing local SQL/Claude files. Worker rollback must not re-enable the invalid quote-buffer signal path for research comparisons.

## Validation references

- Jupiter's current [API documentation source](https://github.com/jup-ag/docs/blob/main/llms.txt) and the app's [current feed implementation](services/vonneumann/vonneumann/market/jupiter_feed.py) establish the tested Price V3 and Birdeye OHLCV consumers; swap access is a separate question.
- [OpenAI model-list API](https://platform.openai.com/docs/api-reference/models/list) and [xAI REST reference](https://docs.x.ai/developers/rest-api-reference/inference) support metadata-only credential checks without generating content.
- [CoinDesk authentication](https://developers.coindesk.com/documentation/data-api/introduction) and [official OpenAPI](https://data-api.coindesk.com/info/v1/openapi) document key-attributed quota validation.
- [Messari lending endpoint](https://docs.messari.io/api-reference/endpoints/protocols/lending/list-lending-protocols) documents the tested product permission; [CoinGecko usage endpoint](https://support.coingecko.com/hc/en-us/articles/6472655452953-How-to-Check-Your-API-Call-Usage-via-Endpoint) and [Demo setup](https://support.coingecko.com/hc/en-us/articles/21880397454233-User-Guide-How-to-sign-up-for-CoinGecko-Demo-API-and-generate-an-API-key) distinguish plan/host choices.
- [LunarCrush API documentation](https://lunarcrush.com/en/developers/api), [CryptoPanic developer page](https://cryptopanic.com/developers/api/), and [Caesar's official SDK](https://github.com/caesar-data/python-sdk) informed the tested/untested boundaries above.


## 17. Portfolio-equity metrics and worker-hosting research (2026-09-30)

**Fitness contract:** `equity-roi-historical-dd-v1` ranks candidates by current portfolio ROI minus twice their observed historical maximum drawdown. The weight of two is retained as a local heuristic, explicitly pending RES-01 calibration. Sharpe, win-rate bonuses, activity bonuses, and the fewer-than-three-trades exception no longer influence breeding. Inactivity has no fabricated loss score. The score is finite or the candidate fails validation; an unavailable diagnostic does not make a liquidatable position unsafe to close.

**Drawdown contract:** each fully valid portfolio observation updates its high-water mark and worst decline from that mark. Current drawdown is a separate value used by the existing death threshold. A path `100 → 120 → 96 → 120` ends with current drawdown zero, historical drawdown 20%, and fitness −0.2. Historical drawdown is the worst **observed** decline; gaps can conceal a worse actual loss. Close plans carry projected peak/worst values immutably; liquidation/replacement preflight and reporting do not mutate history. A partial quote-risk pass can close an eligible position while withholding a complete-equity observation when another held asset lacks an accepted fresh quote. Terminal persistence now retains peak capital as well as drawdown.

**Equity-return diagnostic:** `equity-asof-minute-v1` uses nominal UTC minute endpoints. Paper observations freeze the entire cash-plus-marked-positions value at their actual observation time. An endpoint can use only an observation at or before it, within both the oldest held quote's remaining admissible age and a 30-second observation carry limit. Exact-endpoint observations take precedence; later duplicates cannot revise a published endpoint. Simulation uses its existing modeled minute clock. Historical prices are never combined with current holdings. No trades are required to measure unrealized portfolio returns, and position size matters through equity.

Missing endpoints reset the contiguous segment; they do not produce interpolated or multi-minute returns presented as one-minute returns. The diagnostic retains at most 1,440 contiguous returns, with cached statistics and constant-time long-gap accounting. Metadata records method, nominal endpoint, actual valuation time/age, covered window, return count, missing endpoints, and invalid intervals. A positive-to-zero equity transition yields a −100% return; a subsequent zero denominator breaks the segment. Retirement between endpoints does not invent a shortened one-minute sample; coverage timestamps disclose the final measured endpoint. Capital allocated at birth and reclaimed after retirement is not counted as trading P&L. Future external flows need explicit adjustment.

Sharpe is the mean of same-period excess equity returns divided by sample standard deviation, with an explicit zero-return cash benchmark and **no annualization**. It is unavailable for insufficient observations, zero variance, or unrepresentable arithmetic. Two returns are a computational minimum, not a significance threshold. Even finite near-constant returns can produce a large ratio, which is why the ratio has no breeding weight. Invalid raw inputs fail validation; valid but unrepresentable derived returns break the diagnostic segment. Stable standard-library statistics avoid naive squared-deviation overflow. [Sharpe's original definition and time-aggregation discussion](https://web.stanford.edu/~wfsharpe/art/sr/SR.htm), [Lo's analysis of serial correlation and annualization](https://alo.mit.edu/publications/page/18/), [Python statistics](https://docs.python.org/3/library/statistics.html).

**Storage and UI:** the forward migration `20260930020000_vonneumann_equity_metrics.sql` adds nullable `metrics JSONB` and allows NULL `sharpe_ratio` on `vn_probes` and `vn_fitness_snapshots`. It does not rewrite old records, grant access, change RLS, or label historical scores as new-method scores. Birth/update/terminal/snapshot persistence keeps authoritative values unrounded; presentation owns rounding. Explicit NULL clears a formerly available ratio. The detail view supports unavailable values, identifies the new policy, separates historical/current drawdown, and labels unclassified legacy rows conservatively. Run-level runtime JSON also records fitness/equity/candle policy versions. Stored diagnostic summaries are not a complete restart checkpoint; DB-03 must restore the actual return history, observations, optimizer, ledger, and market state.

**Research still required:** freeze datasets and transaction-cost assumptions; standardize candidate lifetimes and exposure opportunity; measure as-of endpoint lag, stale/gap selection bias, serial dependence and effective sample size; study walk-forward selection, multiple testing, probabilistic/deflated Sharpe and backtest-overfitting controls before choosing thresholds. Use [GIPS flow methodology](https://www.gipsstandards.org/wp-content/uploads/2021/03/calculation_methodology_gs_2011.pdf) when introducing external capital movements. Do not interpret the new score or synthetic replay as profitability evidence. These remain RES-01/ENG-06/FILL-01 gates, not completed research.

**Hosting recommendation:** the dated [worker hosting report](WORKER-HOSTING-RESEARCH.md) compares Render, Railway, Fly.io, and current Vercel Functions/Services. Recommend a paid Render **Web Service in Oregon**, provisionally budgeting 1 CPU/2 GB at $25/month before provider/API and other usage charges. The combined FastAPI HTTP/WS/controller process needs a Web Service rather than Render's network-inaccessible Background Worker. Size and region must be benchmarked; database proximity is not evidence of fastest Solana transaction landing. Vercel now supports Python and WebSockets, but its bounded/stateless execution is not a direct home for this process-local continuous loop.

TODO HOST-01 through HOST-07 cover durable recovery, fenced single-writer ownership during deploy overlap, a pinned Linux image, region/capacity/drain measurements, shared quotas and budget alerts, private secrets/browser URLs, operational drills, and a bounded paper pilot. The report explicitly calls for deeper latency, quota, billing, and market-quality research. Helius's current official credit table and RPC documentation index disagree about `getBlockTime` billing; resolve the intended plan before budgeting. No worker service, hosting account, paid plan, credentials, colony, wallet, signing, swap, or live-trading operation was created by this research.

**Verified migration result:** only `20260930020000_vonneumann_equity_metrics.sql` was applied to the exact allowed Supabase project; its migration ledger now has thirteen versions and a subsequent dry run has no pending work. Before/after catalog comparison confirms exactly two added nullable JSONB columns and two Sharpe nullability changes. All eighteen policies, five RLS flags, indexes, constraints, and trigger definitions/bindings are unchanged. The copied-schema rehearsal and the post-application temporary-table contract pass, ending in ROLLBACK. Both zero-row PostgREST reads return HTTP 200 and an empty result for `metrics,sharpe_ratio`. No public/auth application records were inserted, rewritten, or deleted. The DO migration emitted no prior standalone-SET-LOCAL warning; its explicit lock setting was checked in the rehearsal. Full CLI/history failure atomicity and timed lock contention remain untested and are not claimed.

Two simultaneous linked CLI checks caused one temporary-role authentication sequence to fail and retry while the other completed. Its identified process was stopped; a later sequential attempt succeeded. Subsequent checks and the migration ran sequentially. This is consistent with the CLI's project temporary-login state being refreshed concurrently; no shared user login/logout, credential rotation, other project's configuration, or unrelated process was changed. Future linked DB CLI calls are serialized.

**Local validation:** 397 Python tests, 42 Node tests, TypeScript, and an isolated Next production build pass. Lint reports zero errors and 33 existing warnings. New regressions cover endpoint causality/gaps/constant returns/zero equity/extreme arithmetic, bounded cached statistics, historical-drawdown recovery, unequal exposure size, pure liquidation preflight, nullable/precise persistence and legacy UI labels. An independent review found and repaired the quote-age boundary between eligibility and equity observation: a newly expired held asset is removed from execution eligibility while fresh sibling risk checks still complete. Tests use offline fixtures; builds use fake environment values in a separate temporary directory. This does not constitute a hosted worker, authenticated production browser/worker test, real market backtest, or RLS write test.

**PR #9 Git deployment finding:** the source commit `5f9a2bb36ed4c0f19106e7586f79e3be9e05661b` produced an automatic preview attempt on the correct project, `dpl_HDoghviBpetx2qpET6YgAAhPBHN3`. Vercel reports BLOCKED / `TEAM_ACCESS_REQUIRED` because GitHub author **RedJester14** (ID `273486220`) is not recognized as permitted to create deployments for this team. This is an access/configuration block before a successful preview, not a failed local build. [Vercel's collaboration guidance](https://vercel.com/docs/deployments/troubleshoot-project-collaboration) requires verifying the author's Git provider connection and applicable team membership. RELEASE-01 now records this more specific current evidence. No author rewrite, shared Git/account setting, seat purchase, membership/installation change, or alternate upload to evade this block is authorized by this repair. The normal user-authorized GitHub merge path may be evaluated, but its production result must be verified independently; the PR8 READY alias remains the last verified baseline until then.


## 18. Isolated GitHub identity and deployment authorization (2026-09-30)

The user identified **biggrizzly11** as the GitHub account connected to the intended Vercel account, created a dashboard token, and stored it in macOS Keychain service `codex-dashboard-github-biggrizzly11`, account `biggrizzly11`. Read-only requests using that credential confirmed login `biggrizzly11`, immutable user ID `16749816`, repository `TOOTRJ/TheDashboard`, immutable repository ID `1141090963`, and repository push permission. These metadata checks confirm identity/access; the token's complete permission/selected-repository configuration is not exposed by those endpoints. No secret is written to this repository or printed.

GitHub separately confirms active organization-owner membership. The user's policy screenshot showed fine-grained tokens allowed, administrator approval retained, and a 366-day maximum lifetime. No organization token policy was changed. The intended token setup is a 30-day fine-grained token limited to TheDashboard with Contents/Pull requests write and automatic Metadata read. The account's email for new commits is taken from an existing repository commit that GitHub already attributes to that exact account (`2354ccf8d142aa37808b9f86e67aa1617286a9ce`); the private address is deliberately omitted from reports. This repository alone receives the local Git identity override. Old commits are not rewritten.

`scripts/dashboard-github.py` supplies repository-pinned Git fetch/push and GitHub PR/read-only API operations. It retrieves the dedicated Keychain credential into memory, verifies identity and target, and injects authentication only into its own child processes. An isolated temporary GH_CONFIG_DIR is not sufficient by itself: GitHub CLI login/switch can still update shared Keychain state, so this workflow does not invoke login, logout, switch, or setup-git. Shared/default GitHub authentication and global Git identity remain unchanged. Git push uses an explicit codex branch and checked origin URLs. Credential-bearing Git fetch/push use a command-specific credential helper, no submodule recursion, and no local hooks or automatic maintenance that could inherit the token. Sixteen offline tests cover identity/target mismatches, inherited credentials/tracing, missing/invalid credentials, branch bounds, PR/API scoping, and sanitized failure handling. A real read-only run of the helper independently confirmed the intended identity/repository; the shared default GitHub CLI still identifies as RedJester14.

Before this release, fresh provider metadata again matched Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` / team `team_8iNNxiNjrOseD4gdSCHkQEzF`, linked repository ID `1141090963`, and Supabase `The Dashboard` / `fxpxsciltakyypunglzr` / organization `cqfnnaunmupdyobkyqfo`, ACTIVE_HEALTHY. The production alias still resolved to the PR #8 READY deployment. The PR #9 production attempt `dpl_BFBqjGDNDqyEsn729BsJCk3wzoTd`, merge commit `b2be27cfc8f216cb03ce80606b205124fee478ef`, remained BLOCKED / TEAM_ACCESS_REQUIRED for RedJester14. A successful credential check alone is not deployment evidence: the new commit's GitHub attribution, automatic preview, exact merged source SHA, and production alias must each be verified before RELEASE-01 is completed.

During release preparation, the previously unavailable Next.js security patch became available. The accompanying dependency follow-up updates Next.js and eslint-config-next from 16.3.7 to 16.3.8; React stays on 19.2.8. Details, upstream limitations, and fresh frontend validation are recorded in DEPENDENCY-REVIEW.md. This continuation changes no schema, Vercel/Supabase settings, shared credentials, team membership, billing, or other projects. Its release includes PR #9's already-tested application changes through normal Git ancestry. No worker, colony, live wallet, signing, or swap is started. The intended rollback is a corrected forward release preserving the nullable-metrics UI/schema contract; PR #8 is the previously served frontend but would not safely display newly persisted NULL Sharpe records once a worker exists.

**Verified PR #10 release:** GitHub attributes source `d945dcdea7fbc3fffe7dede218ffaab9f740579d` to biggrizzly11 for both author and committer. The normal Git integration built preview `dpl_99zV4MVWj8Xu312AEvASESgMj28f` to READY. PR #10 was merged by biggrizzly11 at `2026-09-30T21:42:58Z` as `e9045b4f133f81fc75d5552e531c43a6259c3500`. Automatic production deployment `dpl_EqbEvGzqe3RK7CD5mLscyf32SmiQ` is READY on that exact merge and project/team; the public production alias independently resolved to it at verification. Its deployment URL is `https://the-dashboard-ompszkt59-orderoftheredjester.vercel.app`. The release includes the already-merged PR #9 frontend plus the new security patch; no new Supabase migration was required.

Read-only production smoke checks return `/login` 200, `/` 307 to `/login`, unauthenticated `/api/v1/test?limit=0` 401, and authenticated same-path 200 with success and zero rows. The initial authenticated smoke script expected `.env.local`; the key was instead found in the existing root `.env`. The script was corrected without editing either credential or environment configuration, and the final complete check passed. A project/deployment-pinned error-level log query since merge returned zero records (limit 100); this is a bounded initial check, not sustained monitoring. The token's GitHub combined status-check query was unavailable, so preview/production acceptance used verified Vercel API evidence without adding permissions. Sixteen offline helper tests, 42 frontend tests, TypeScript, clean installation, and an isolated Next 16.3.8 build passed; full/production npm audits were zero and lint retained 33 pre-existing warnings. Shared GitHub login remained RedJester14 after the isolated operations.

RELEASE-01 is complete. ENG-05 risk-breaker behavior is the next engine priority. SEC-05 retains the two deferred upstream Next vulnerabilities, and worker hosting, safe restart/ownership, preview isolation, browser/worker acceptance, realistic execution, and the researched minimal-gene experiment remain separate open work.


## 19. Circuit breaker and explicit risk recovery (2026-09-30)

**ENG-05 local completion:** the former breaker checked losses after entry/reproduction decisions and then raised at the start of the next tick, stopping fresh valuation and protective exits while positions could remain open. A separate `risk_halted` lifecycle now blocks new risk while keeping the supervised quote/risk loop active. This is an entry halt with existing protective exits, not an immediate liquidation instruction. Stop still retains owned positions for reconciliation; it never fabricates a fill.

**Loss contract:** `initial-account-loss-v1` compares reserve plus every owned probe's cash and freshly marked holdings against the initial whole-account equity. The default remains 30%; crossing or equaling the limit trips. Reserve belongs in this stated account policy, while cumulative recycled `total_deployed` does not. For example, a $500 loss from a $10,000 starting account is 5% account loss even if only $1,000 was allocated to candidates. This is neither a 50% deployed-capital limit nor a peak-to-trough drawdown policy. The UI names the denominator. The baseline stays fixed through recovery and a new trip receives a fresh UUID.

**Decision order and persistence:** each tick first supplies accepted quotes and completes every eligible probe's protective pass. It then values account risk and latches before awaited writes or decisions. Completed protective-close events still persist if the final account valuation expires/fails. A trip blocks pending entries, self/strategy reproduction, diversity injection, replacement births, and death refills. Stop-loss, take-profit, terminal drawdown and hard lifespan exits remain available under valid fresh quotes. Lifespan expiry also precedes otherwise profitable reproduction. Halted ticks skip candle retrieval; their quote protection does not depend on candle-provider availability. Invalid quotes or failed persistence still follow the existing explicit terminal failure path and require reconciliation rather than pretending monitoring continues. If all candidates die while halted, cash is reclaimed once, the halt remains visible, and no empty-population refill occurs.

Runtime JSON stores the breaker flag and whitelisted risk metadata: policy, threshold, baseline, observed equity/loss/time, trip ID/time/equity/loss, recovery time and count. A direct owner-scoped persistence callback acknowledges transitions before circuit-breaker/status notifications; notification events deliberately do not issue duplicate status writes. The existing status column is unconstrained text and runtime is JSON, so **no DDL or new Supabase migration** is required. These saved diagnostics are not a full process-restart checkpoint or an append-only event ledger; DB-03 remains mandatory for restoration, uncertain-write reconciliation, outbox/replay semantics and fenced ownership.

**Recovery contract:** `POST /api/v1/colonies/{id}/recover` is authenticated and owner-scoped, accepts only a strict UUID-shaped `trip_id`, and uses the same bounded, cancellation-safe manager serialization as other controls. The controller holds its tick lock while verifying the exact active trip, surviving candidates, complete fresh quotes, and equity strictly above the original loss boundary. It refreshes valid candle history while still latched, persists the prospective recovery, and verifies quote freshness again. If the write outlives its quotes, it compensates the saved status without ever unlocking new risk. It clears pending intents and establishes a recovery-time candle boundary so old or halted-period signals cannot execute afterward. Expected refusal returns a sanitized 409 and preserves risk monitoring. Unexpected failures return the existing safe 503/failed state. Failure or cancellation during recovery notification stops the loop inside the tick lock, preventing a waiting tick from running before the manager handles the failure; acknowledged recovery metadata is retained truthfully.

Ordinary pause/resume cannot clear or suspend a risk halt. A trip racing an already-requested pause is preserved and protective monitoring resumes. Stop and shutdown accept halted colonies. The dashboard offers separate Recover and Stop actions, suppresses duplicate controls while pending, and waits for worker status instead of optimistically changing to running. Recovery requires a currently confirmed halt and validated trip ID; a saved halt or an outage explicitly cannot confirm ongoing protection. All six refusal codes use local explanations instead of reflecting arbitrary server messages.

**Research basis and follow-up:** Freqtrade documents an entry-pause that continues managing open trades and allows only reductions in position size; its documented pause is not persisted across restarts. That supports separating entry permission from position management, but is not a complete restart design for this worker. [Freqtrade control documentation](https://docs.freqtrade.io/en/stable/telegram-usage/#pause-stopentry-stopbuy). CME's kill switch separately cancels specified working orders and prohibits new entry, illustrating that cancellation, entry prevention and position liquidation have distinct semantics; this implementation does not claim CME behavior or coverage. [CME kill-switch documentation](https://www.cmegroup.com/tools-information/webhelp/globex-credit-controls/Content/Kill-Switch.html). Deeper research remains needed on loss-policy calibration, account versus allocated-capital/peak loss, recovery hysteresis and cooldowns, correlated asset shocks, gap/stale-feed behavior, liquidation costs, and operational restart/outbox guarantees. Preserve these as RES-01/FILL-01/DB-03/HOST dependencies before any live design.

**Validation:** all **430 worker tests and 52 frontend tests pass**, including 33 new worker and 10 new frontend regressions. Coverage includes exact thresholds and reserve denominators, protective stops/take-profit, drawdown/lifespan precedence, no births while halted, all-dead cash conservation, trip/recovery persistence failures, stale-after-acknowledgement compensation, old-signal exclusion, queued ticks during failed/cancelled notification, pause/stop races, cancelled callers, ownership and strict request validation, and saved/outage UI. Full TypeScript and an isolated default-Turbopack Next 16.3.8 production build pass. Broad source/test lint reports zero errors and 33 existing warnings. Tests deny network/database access; the separate build uses fake configuration and preserves the repository's original build output. Independent frontend/backend review also checked the controller and found the two repaired event-preservation/concurrency edges. No live colony or worker was started.

**Release preflight and rollback:** immediately before publication, read-only verification matched GitHub `TOOTRJ/TheDashboard` / `1141090963`, Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` / team `team_8iNNxiNjrOseD4gdSCHkQEzF`, and Supabase `The Dashboard` / `fxpxsciltakyypunglzr` / organization `cqfnnaunmupdyobkyqfo` (ACTIVE_HEALTHY). The pre-release production alias is READY on PR #11 merge `bdd07d41901f9ce9200e9b9cdba2780770db3ab3`, deployment `dpl_H31sC4rYD3kdUfdLrCaEMz5AHYAm`. Release through a codex branch/PR and the normal authorized Git integration, verifying its exact source and merge deployments before accepting production. Read-only login/redirect and zero-row authenticated API checks cover the frontend release; there is no hosted worker endpoint for browser-to-worker acceptance. Prefer a forward fix if halted records ever exist because the older frontend lacks this status. Never roll an active worker back to the broken breaker; retain failed/halted accounts for reconciliation. Cloud credentials, shared settings, other projects, and the pre-existing historical migration/Claude files remain outside this change.


## 20. Comparable optimizer cohorts (2026-09-30)

**ENG-06:** the previous live-survivor list could shrink a CMA population between ask and tell, and repaired genomes were incorrectly reconstructed as the original ask vectors. Quote-tick reproduction/lifespan clocks could also expire during indicator warmup. Built-in optimizers now use `common-market-window-v1`: the controller creates fixed ordered groups with distinct iteration/evaluation identities, waits for every configured candidate asset's complete current RSI/EMA/volume inputs, then starts one common market-time evaluation window. Until readiness, candidates hold their cash and cannot open entries, reproduce, or expire from the evaluation-age limit. The start cancels earlier signals. Legacy serialized `reproduction_interval` and `max_lifespan_ticks` now mean market minutes, with the latter measured after readiness; launch labels and saved policy make this semantic change explicit. Custom internal test strategies retain their legacy scheduling contract.

Every candidate has one terminal result. Early protective/lifespan deaths retain their frozen account return/drawdown score and cash through the common deadline, while other candidates continue. No spontaneous reproduction, diversity injection, or replacement can change membership mid-window. Even an all-dead group waits for its deadline and remains accounted for. Completion uses the first valid observation at or after the nominal deadline and records its actual time; no historic exact-deadline price is fabricated. New groups use fully preflighted, equal seed budgets and reset accounts. During this prerequisite release a bounded controller adapter also clones unevolved survivors; GA and DE algorithm-specific selection remains ENG-07.

The ledger snapshots phenotypes and rejects changed candidates, duplicate/foreign/missing results, invalid scores, and early or repeated group completion. Only finalizing the entire group at its deadline grants completion proof to its immutable results. Aborted groups, including all-dead groups, never receive that proof. CMA retains a copy of each original ask vector, binds the ordered generated phenotypes to the actual spawned IDs, and tells the exact complete vector/score batch once, independent of result order or early death. Initial random candidates establish the bootstrap mean rather than pretending they came from ask. The installed library is **CyberAgent `cmaes` 0.13.1**, not pycma. Its [official usage](https://github.com/CyberAgentAILab/cmaes#usage) evaluates each asked vector and passes that vector to tell; its [versioned implementation](https://github.com/CyberAgentAILab/cmaes/blob/v0.13.1/cmaes/_cma.py) requires the fixed population size. [DEAP's algorithm documentation](https://deap.readthedocs.io/en/master/api/algo.html) likewise separates generation, evaluation, and update. This release does not claim solver convergence on a changing market objective.

Pausing, tripping the account breaker, stopping, or failing aborts the group without an optimizer update. Resume/recovery schedules fresh equal-budget accounts and a new optimizer epoch on the next valid quote batch, with full funding/capacity preflight before closing an old holding. This can legitimately fail if losses leave insufficient funding; it never resets the whole-account loss baseline. The PSO ID remap now includes early-dead parents, and abort clears its old state; cross-window personal/global-best comparison is still repaired separately under ENG-09. Quote/risk precedence and the ENG-05 halt remain in force throughout.

Owner-scoped runtime writes acknowledge group start, completion, and next-group binding before status notifications. Saved JSON contains the versioned policy, active group, and latest completed/aborted group, using existing columns with no migration. It is bounded recent diagnostic state, not an append-only result ledger or an executable restart checkpoint. Frontend parsing allows only recognized policy fields and safe progress summaries; it excludes raw candidate/member records from the display model and labels worker-outage data as historical. Full restart restoration remains DB-03/HOST work.

**Validation:** 463 offline worker tests and 58 frontend tests pass, including 17 ledger/CMA regressions, 16 controller integration cases, six new UI cases, and the adapted 60-cycle real-optimizer funding checks. Controller cases use real CandleHistory and real CMA, cover one/all early deaths, compare two versus 120 polls on the same market window, exercise actual circuit trips, interruption/restart, late marks, invalid phenotype and inadequate funding. Independent review caught and fixed reserve credit occurring before terminal-result validation, which could otherwise double-count retained dead-account cash. TypeScript and isolated Next production build pass; broad lint retains zero errors and 33 existing warnings. No worker/colony, database write, or live transaction was started by verification.

**Research and remaining gates:** determine appropriate warmup and horizon lengths for each timeframe, how to bound late observations and sparse/no-volume readiness, and sensitivity to unequal trading opportunity, regime changes and interruption selection bias. A complete zero-trade window is usable mechanical evidence, not proof of strategy quality. Realistic costs, immutable datasets, objective calibration/multiple-testing controls, durable results/checkpoints, and optimizer RNG ownership remain necessary. ENG-07 follows with bounded GA and paired same-window DE; ENG-08/09 cover actual phenotype domains and normalized solver coordinates; ENG-10 completes independent seeded search streams; ENG-11 finishes history/lineage/retention.

**Release boundary:** target verification must again resolve GitHub `TOOTRJ/TheDashboard` / `1141090963`, Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` / `team_8iNNxiNjrOseD4gdSCHkQEzF`, and Supabase `The Dashboard` / `fxpxsciltakyypunglzr` / `cqfnnaunmupdyobkyqfo`. PR #12 merge `5b0036dc091563dee857d34447fa25c4306b276d`, READY deployment `dpl_CabjSr5LdehvfkCye4LmcVJkrN6z`, is the preceding frontend baseline. Verify this section's exact preview/merge/production alias and read-only smoke checks in its PR. Roll forward if cohort records exist; old clients do not interpret the new scheduling policy. The worker remains unhosted, and deployment does not imply browser-to-worker or restart acceptance.


## 21. Bounded GA and paired differential evolution (2026-09-30)

**ENG-07:** GA now accepts complete finite common-window evidence for every bound candidate, including losing and zero-trade windows. Tournament parents come only from that group; even two candidates produce exactly two children. Each full replacement has the same account count, with no top-30% parent-count dead zone or accidental growth. Actual crossover children record both participating parents, while cloning/fallback children record one. Asset unions have deterministic ordering. The controller rejects incomplete/oversized proposals before retirement rather than silently truncating or inventing children.

DE now implements deferred DE/rand/1/bin selection with paired simultaneous target and trial accounts. The launch count denotes actual funded accounts: it must be even and at least eight, providing at least four incumbent slots and four trials. Initial random accounts establish the incumbents; every later group evaluates target clones and trials on the same common market window. A trial replaces its paired target only when its current score is strictly better; ties keep the target. Historical target scores and incomplete evidence are never reused. All winners are frozen before new donors are sampled, and losing trials cannot supply the next generation. Trial metadata identifies target/base/positive-difference/negative-difference roles. Only active coordinates can receive the forced donor coordinate. With no active coordinates, trials are explicit clones. GA/DE binding rejects foreign, duplicate, altered, partial, premature, repeated and overlapping-window evidence. Abort discards the pending selection state.

API and browser validation enforce the actual DE funding/capacity requirement before starting a run; the dialog explains the account pairing. Selection policy, pair scores/decisions and ancestry are retained in the latest completed runtime evaluation using existing JSON. This is bounded diagnostic state, not a durable full result ledger. Until ENG-08, a conservative repair guard falls back to a valid parent if legacy coupled repair would change a fixed/disabled control. That guard does not solve the registry/factory defects; the unified actual-phenotype contract is the next release.

**Research basis:** [SciPy's differential-evolution documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.differential_evolution.html) describes comparing evaluated trials against their targets and deferred population updates. [DEAP's generational algorithm documentation](https://deap.readthedocs.io/en/master/api/algo.html) separates parent selection, variation, evaluation and replacement. Our trading adaptation pays explicitly for concurrent target re-evaluation because successive market windows are different objectives. A full zero-trade window is valid mechanical evidence, not evidence of profitability. Further research should compare equal-account/equal-evaluation budgets across solvers, pairing variance, sparse-trade penalties and horizon calibration after realistic costs and immutable datasets exist.

**Validation:** all 482 offline worker tests and 59 frontend tests pass. Fifteen selection tests cover small/odd populations, negative/no-trade evidence, pair ties and regime changes, losing dead trials, true donor roles, invalid/duplicate/mixed evidence, fresh ordered bindings and abort, fixed-control fallback and a 30-generation deterministic quadratic objective. Real-controller funding tests exercise 60 GA two-account cycles and 60 DE eight-account cycles, preserving funds and complete populations. TypeScript, an isolated production build, and zero-error lint pass (33 existing warnings). No network or database is available to worker tests.

**Release boundary:** read-only checks verified GitHub TOOTRJ/TheDashboard / 1141090963, Vercel the-dashboard / prj_wFUe9k9USVreOQcmQKNWRAVsx5fH / team_8iNNxiNjrOseD4gdSCHkQEzF, and Supabase The Dashboard / fxpxsciltakyypunglzr / cqfnnaunmupdyobkyqfo (ACTIVE_HEALTHY). PR #13 merge d86789c33fb461b162a37951554e347ded659f54 and READY deployment dpl_5bjzosMZGHieBW2sEoC6M64KrYi8 are the preceding baseline. This section's PR records exact source, preview, merge, production and read-only smoke verification. No migration, worker start, trading, shared authentication change or other-project edit is required. Prefer a forward fix; reverting only the browser pairing constraint would make launch guidance inconsistent with the worker.


## 22. Configured actual-phenotype contract (2026-09-30)

**ENG-08:** the registry resolves one effective domain per numeric gene after validating registry bounds, override bounds, explicit defaults/fixed values, enabled controls and asset-pool capacity. Fixed values take precedence; disabled genes lock to an explicit default or the registry default clipped into the configured range. Equal min/max is a locked dimension. Explicit out-of-pool asset counts are rejected, while the implicit default count can shrink for a smaller universe. All presets use the same contract. A disabled gene no longer receives a new random value at each birth.

The actual genome is projected deterministically: finite numbers only, configured bounds, half-up integer conversion before relationships, then fast EMA < slow EMA and stop loss < take profit by adjusting only active partners. An impossible locked pair fails validation before any write or candidate birth. A feasible fixed fast EMA of 15 is accepted when the active slow EMA can become 16 or greater; older validation incorrectly rejected it just because some unprojected slow values were smaller. Strict float ordering uses the adjacent representable value where needed; this is a mechanical constraint, not a calibrated minimum risk/reward spread. The entire projection validates before assigning fields, is idempotent and consumes no randomness. Trading rejects unvalidated fractional integer phenotypes rather than performing hidden later rounding.

Assets retain valid unique preferences and deterministically fill from the configured ordered universe to exactly the final integer count. Random initialization respects fixed counts and uses the declared integer domain for timeframe rather than an unrelated hard-coded subset. Mutation noise scales to the configured active interval. Every factory/operator uses the same validation, including self-reproduction, diversity and the four built-in solvers. ENG-07's conservative fallback remains compatible but should not activate for valid fixed parents under the new contract.

**Validation:** 498 offline worker tests and 61 frontend tests pass, plus TypeScript, isolated production build and zero-error lint with 33 existing warnings. Fifteen contract tests sample hundreds of genomes across all presets/operators, check atomic nonfinite rejection even for locked genes, repeated no-RNG validation, integer/coupled repairs, fixed counts, explicit disabled defaults, and original CMA ask-vector retention. Twenty-six shared JSON fixtures verify browser/API agreement on accepted and refused settings. Controller fixtures now explicitly fix their intended short indicator windows; previously they depended on the bug that disabled controls retained arbitrary fixture values instead of configured defaults.

**Remaining research:** projection changes the sampling distribution and integer regions can map several proposals to one phenotype. Compare repair/rejection and mixed-integer/categorical solvers after equal-budget objective tests, then evaluate cost-aware risk/reward constraints on immutable replay data. ENG-09 normalizes continuous coordinates; ENG-10 records seed/stream ownership. Full checkpoint/result manifests and realistic fills remain later gates.

**Release boundary:** read-only verification again matches GitHub TOOTRJ/TheDashboard / 1141090963, Vercel the-dashboard / prj_wFUe9k9USVreOQcmQKNWRAVsx5fH / team_8iNNxiNjrOseD4gdSCHkQEzF, and Supabase The Dashboard / fxpxsciltakyypunglzr / cqfnnaunmupdyobkyqfo (ACTIVE_HEALTHY). The preceding baseline is PR #14 merge a9ae3c06dffb9aa2e31cdd6ed21436becfcae1d0 / READY production dpl_HbFQy8FQLo7xueZSAzvARzDTbptu. Exact source/preview/merge/production smoke evidence is recorded in this section's PR. No database migration, hosted worker, trading or unrelated-account change is needed. Prefer a forward fix because old runtime factories do not honor the same fixed/disabled controls.


## 23. Normalized optimizers and current-window swarm evidence (2026-09-30)

**ENG-09:** ParameterCodec maps each effective active numeric domain to [0,1], omits fixed/disabled/singleton domains, and rejects unvalidated phenotypes or geometry changes during an epoch. Decode uses ENG-08's canonical integer/coupled repair and deterministic ordered asset inheritance/resize. Bad dimensions, mixed booleans, strings and nonfinite coordinates fail before sampling/state updates; clipping is explicit for swarm proposals. The continuous vector does not pretend to optimize asset identity. CMA uses the best current candidate's ordered asset template; swarm particles inherit their own assets.

CMA now starts with sigma 0.3 in unit coordinates and bounded unit asks, instead of applying one raw deviation to minute, dollar and fractional-risk genes. It tells the original sampled arrays bound to the evaluated phenotypes, including after integer/constraint projection. No active dimensions produces a full evaluated clone group rather than an empty proposal. Bootstrap identities remain fixed even without a numerical optimizer; generation changes invalidate candidate bindings; ties select asset templates in original bound order. Ancestry records the current evaluated distribution-source cohort, with the asset-template source separately identified. This represents distribution contributors, not sexual mating or a claim that any one parent uniquely produced the numerical sample.

The swarm is explicitly labeled **Window-reset Swarm (PSO variant)**. Historical personal/global fitness scores are incomparable across different market windows. Each completed group rebuilds its best evidence solely from that common window, even when all scores are negative. With one observation per particle in a window, personal best is the current position and the cognitive term is zero; this variant uses inertia plus current-window social attraction. Initial private normalized velocities in [-0.1,0.1] avoid immediate zero-motion collapse. Stored momentum equals encode(repaired child) minus encode(parent), including bounds and integer rounding. Fresh account scores are unknown until evaluation, and velocity/state IDs are remapped one-to-one and cleared on abort. Parent roles identify the particle first and a distinct contributing social source when present.

**Validation:** 515 offline worker tests and 61 frontend tests pass, with TypeScript, isolated production build and zero-error lint (33 existing warnings). Seventeen new codec/geometry/objective tests exercise real cmaes 0.13.1 and the actual swarm on Sphere and a rotated anisotropic quadratic, affine domain-rescaling invariance, zero/one active dimensions, bounds, repaired-vector identity, changed-regime score reset, duplicate/partial evidence, early-terminal remapping, source ancestry and stable tie ordering. A seeded 1,000-ask default-domain comparison illustrates the raw-scale problem: about 51% of raw-sigma coordinates hit an endpoint versus about 1% with normalized sigma, before discrete phenotype repair. These are numerical geometry measurements, not trading results or tuning guarantees.

**Research basis and limits:** [CMA scaling guidance](https://cma-es.github.io/apidocs-pycma/cma.evolution_strategy.CMAEvolutionStrategy.html) supports comparable parameter sensitivity; the installed implementation is [CyberAgent cmaes 0.13.1](https://github.com/CyberAgentAILab/cmaes/blob/v0.13.1/cmaes/_cma.py), not pycma. [PySwarms handlers](https://pyswarms.readthedocs.io/en/latest/api/pyswarms.handlers.html) describe handling boundaries/adjusting motion. Our best reset is a local policy for changing market objectives, not a source-endorsed trading strategy. Integer projection can stall momentum and multiple vectors can share a phenotype. Research mixed-domain solvers, duplicate handling, explicit reheating/discrete moves, re-evaluation of historical bests with matched budgets, dynamic-regime adaptation and appropriate common-window duration on immutable datasets with realistic costs. Do not silently add noise or old scores to bypass these issues. ENG-10 next establishes reproducible seeded search streams.

**Release boundary:** verify the same pinned GitHub, Vercel and Supabase IDs/owners before release. The preceding baseline is PR #15 merge 0015bce546208ecdd074a9980a9e6e06d2ae9faf / READY production dpl_FbWKmm78TstfiWq5eobQfLgrAY9N, with read-only smoke checks passed. This section's PR records exact release evidence. No schema migration, worker/colony start, live trading, shared credential or other-project edit is required. Prefer a forward fix to preserve candidate/coordinate policies.

## 24. Private search streams and replay specification (2026-09-30)

**ENG-10:** a canonical unsigned 64-bit decimal-string `search_seed` (default `"0"`) now drives owned SHA-256-namespaced streams. Initial candidate/index streams are common across algorithms; algorithm/epoch strategy streams, generation/event/candidate mutation streams, and the private CMA seed are separate from synthetic market streams. Legacy standalone helpers use private deterministic generators rather than process-global randomness. UUIDs, names, Python hash randomization and wall time do not determine search seeds. A successful explicit restart increments the search epoch; normal completed windows continue their owned streams.

API/browser validation preserves the full integer range without JavaScript number rounding. The advanced dialog exposes the seed and explains that changing it leaves the market path unchanged. Versioned `search-spec-v1` metadata records the stream, genome/parameter policies, strategy, epoch and simulation specification in existing configuration/runtime JSON. Dashboard live and saved history show the validated seed/epoch and the restart limitation. Ordered bindings and asset unions keep callback/hash ordering out of selection.

**Validation:** all 524 offline worker tests and 63 frontend tests pass, plus TypeScript, isolated production build and zero-error lint (33 existing warnings). Nine dedicated tests run all four real controllers through replay, interleaved colonies, unrelated Python/NumPy random draws, changed wall pacing and fresh Python hash-seed processes; changing only the search seed changes genomes while preserving market frames. API validation/propagation and restart epochs are covered. Independent review additionally reproduced five windows for all four solvers with all 15 active genes, changed candidate IDs and reversed result delivery.

**Research and limitations:** [NumPy's parallel RNG guidance](https://numpy.org/doc/stable/reference/random/parallel.html) motivates independently owned deterministic streams, while this implementation uses versioned SHA-256 semantic namespaces and Python/CMA generators. Replay covers economic candidates and account/market behavior with identical configuration, data, software and lifecycle events; it excludes display names, UUIDs and wall-clock timestamps. A seed cannot recreate unspecified paper feed input or changing dependencies. Metadata explicitly says optimizer state is not checkpointed. DB-03 must persist complete RNG/optimizer/account state and immutable input/result manifests before crash recovery; compare stream policies and cross-version compatibility in further research. No statistical independence or trading-profit guarantee is claimed.

**Release boundary:** exact GitHub TOOTRJ/TheDashboard (1141090963), Vercel the-dashboard (prj_wFUe9k9USVreOQcmQKNWRAVsx5fH; team_8iNNxiNjrOseD4gdSCHkQEzF) and Supabase The Dashboard (fxpxsciltakyypunglzr; cqfnnaunmupdyobkyqfo) were verified read-only. Baseline is PR #16 merge 574fe4d2167730bfac449c88f4100648b955b91c / READY production dpl_4KjYbquCuRvvUxgi74kPRnX9V1Rz. The section PR records exact deployment evidence. No migration, worker start, funding/trading, shared authentication or other-project change is required.

## 25. Acknowledged lifecycle, lineage and bounded history (2026-09-30)

**ENG-11:** repository persistence no longer treats `probe_dying` or `probe_reproducing` as death. They save their actual intermediate state; only a complete finite `probe_dead` event records final capital, peak, lifetime metrics, reason and event-time death. Retirement emits its explicit terminal summary before reclamation. Trade closure events remain ordered before terminal persistence. Selected ancestry sources and culled candidates have distinct reasons; a mate appears only for an actual crossover and every numerical source is retained. The legacy scalar parent remains the first source for compatibility.

Cash ownership changes only after terminal persistence succeeds and all aggregate/reserve calculations succeed. The archive stages a copy of generation statistics and compensated reserve arithmetic before committing ownership, preventing a partially failed aggregate from counting the same cash in reserve and the registered account. Failed births remain unacknowledged; a failed terminal or generation write cannot mark completion. A generation completes only after future births are sealed and every acknowledged member has an acknowledged terminal record. New children can never join a sealed birth epoch; generation is explicitly not ancestry depth. `reproduced_count` counts distinct sources with acknowledged children before completion; later use of a historical source is recorded in child ancestry without rewriting a completed summary.

Memory limits are 256 recent closed trades per probe, 500 recent dead probes, and 100 completed-generation ID markers. Evicted trade aggregates preserve lifetime count, wins and P&L. Lifetime terminal/total counts do not fall when dead objects are evicted. Pending generation summaries use online moments over the full birth population, independent of recent caches: RMS pairwise numeric distance normalized by global registry ranges, excluding categorical assets. This differs from current-population mean gene/asset distance. Completed aggregates are removed only after persistence acknowledges the summary; current-cohort parent-generation bindings retain needed early-dead ancestry through cache eviction. Persisted history is not deleted by cache limits.

The dashboard handles terminal events explicitly, preserves sparse-update data and all source arrays, and prevents a delayed database read from undoing newer lifecycle/generation events. An open detail dialog follows current probe rows. Intent states have pending labels and cannot display a death time before the terminal event. Genealogy uses a flat birth-generation/source list to avoid expanding dense multi-parent graphs; legacy empty parent arrays fall back to genome/scalar sources and missing parents remain visible as outside loaded history. Summary counts distinguish last reported lifetime values from loaded rows. Versioned lifecycle policy is persisted in existing runtime JSON and validated before display; missing legacy policy is not guessed. Application documentation now describes the actual completed-candle, cohort, GA/DE, normalized CMA/swarm, seed and lifecycle behavior.

**Validation:** 543 offline worker tests and 75 frontend tests pass, with TypeScript, isolated production build and zero-error lint (33 pre-existing warnings). Lifecycle regressions cover intent versus terminal persistence, final metrics and source arrays through fresh repository readback, failed reproduction, terminal/birth/generation writes, aggregate arithmetic failure without double credit, same-generation refill, old surviving sources, early-dead lineage after eviction, long-running bounded state and independently calculated pairwise RMS. Frontend regressions cover intermediate/final/sparse events, stale read ordering, legacy/malformed ancestry and current detail display. All integration tests use offline/mocked persistence; no live worker or colony is started.

**Remaining research and operational gates:** old rows marked DEAD from transition intent cannot safely be repaired without terminal evidence; prepare a separately reviewed reconciliation report under DB-03. A new repository reading saved rows is not executable worker restart restoration. Durable event/outbox transactions, command idempotency, account/optimizer/RNG checkpoints and immutable result manifests remain required. Research birth-epoch attribution after interruptions, numerical source roles, diversity comparability and appropriate history paging/retention. Realistic fees/slippage and rigorous objective/dataset/multiple-testing protocols precede the two/three-gene baseline and any claimed strategy quality. Worker hosting recommendations remain in WORKER-HOSTING-RESEARCH.md and HOST-01 through HOST-07; no new provider or live-trading setup is included here.

**Release boundary:** pinned GitHub TOOTRJ/TheDashboard 1141090963, Vercel the-dashboard prj_wFUe9k9USVreOQcmQKNWRAVsx5fH / team_8iNNxiNjrOseD4gdSCHkQEzF and Supabase The Dashboard fxpxsciltakyypunglzr / cqfnnaunmupdyobkyqfo are verified before release and again before merge. Baseline PR #17 merge 42bfe880f8d68b54766351313e8a1113f146b66b is READY as dpl_Dn4gsnzsSvAGWQCTG4kf1xVSNS4v with all four read-only production smoke checks passed. The ENG-11 PR records exact release evidence. These changes use existing schema and require no migration. No other project, shared authentication, credential rotation, worker start, wallet funding/signing or trade is changed. Preserve previous-policy history and prefer a forward fix if reconciliation exposes a defect.

**Phase 2 release closure (2026-09-30):** ENG-05 through ENG-11 were released as PRs #12 through #18, each after exact target verification. PR #18 source 39bb66461ffa1885c1fba29bd7c5b7fe7259fd31 had READY preview dpl_9pciWmbZcjCFEFbBd115KGTs5rD3 and merged as a7f738436de7cc9403c78943100cfce900bfdd0d. Production dpl_J3ujQs6XxZp9kvfutM3mz9ZqRfB8 and the production alias are READY at that merge. Login returns 200, root redirects to login, unauthenticated API returns 401 and authenticated zero-row API returns 200. All 12 Phase 2 entries are complete; tested source equals main and the pre-existing local SQL edit is preserved byte for byte. The handoff-only documentation follow-up updates stale Phase 3 descriptions without changing application code or closing remaining data/recovery/hosting gates. Its PR records its exact deployment evidence.


## 26. Immutable offline fixtures and synthetic playback (2026-09-30)

**DATA-01B scope:** canonical manifest/JSONL bundles identify exact input bytes and declared units, source times, receipt/availability times and ordered asset identities. Strict bounded loading rejects malformed, altered, incomplete, reordered, future, conflicting or incompatible records. Exclusive publication preserves existing datasets. The offline CLI generates synthetic fixtures without provider requests or credentials. Replay advances a complete frame for every nonempty quote batch, delivers only previously available canonical candles once, and fails explicitly at exhaustion. The controller uses modeled time, rejects replay in paper mode and retains dataset identity in existing search-spec runtime JSON. No public file-path API is introduced.

**Limits:** synthetic playback only, with no experiment warmup partition and the complete declared evaluation span. Provider-normalized archives can be validated but cannot drive replay. Source/receipt ordering is deliberately stricter than the live two-second future tolerance; acceptance does not assert freshness or authenticity. A rights declaration is not contractual verification. These are immutable test fixtures, not a representative historical dataset, a cost-aware execution simulator, or a durable result/checkpoint ledger. See [the format and playback contract](services/vonneumann/MARKET-DATA-CONTRACT.md). DATA-01, DATA-02, RES-03, FILL-01 and DB-03 remain open for those requirements.

**Research basis:** Jupiter V3 returns USD reference prices and may omit unreliable tokens; an amount-specific swap quote is a different contract. Its OpenAPI defines createdAt as token creation time and includes an illustrative USDC price of 0.9999, not a guaranteed dollar peg or a current measurement. Preserve block/source time separately from receipt and reconcile USD cash/value assumptions before USDC return claims. A pointwise reference conversion requires synchronized token/USD and USDC/USD observations. Independently dividing OHLC extrema cannot reconstruct ratio extrema. Sources: [Price V3](https://developers.jup.ag/docs/price), [official schema](https://developers.jup.ag/docs/openapi-spec/price/v3/price.yaml), [pricing methodology](https://developers.jup.ag/blog/how-jupiter-prices-a-token), and [estimated Solana block time](https://solana.com/docs/rpc/http/getblocktime).

Birdeye's August 26, 2026 changelog introduced market-cap candles in the same OHLC fields. The existing adapter already explicitly pins chart_type=price, currency=usd, ui_amount_mode=raw and padding=false; those are implemented controls. v is token volume, while v_usd is USD volume. Raw UI mode does not establish integer atomic units: the provider's scaling examples include fractional OHLCV volume. The chart guide discusses a forming latest bar; it does not establish a bound on publication delay or immutable completed candles. Sources: [official changelog](https://birdeye.so/data-api/changelog), [TradingView integration guide](https://birdeye.so/data-api/blog/detail/solana-tradingview-chart-api-birdeye-data), and [Token-2022 scaling documentation](https://bds-support.birdeye.so/hc/en-us/articles/48443824197785-Birdeye-Now-Supports-Scaled-UI-Amounts-for-Solana-Token-2022).

**Further substantial research, in order:** (1) Establish this account's actual archival, internal replay, export, collaborator and retention rights before collection; Birdeye's general terms contain restrictions and permit applicable supplemental terms to control. An API key alone does not prove those rights. (2) Resolve historical coverage/survivorship, timestamp boundaries, publication distributions, older revisions, point-in-time filtering, scaled units and raw/query/parser provenance through authorized fixtures and provider evidence. A download today cannot establish when historical values were first available. (3) Specify recorded wall/monotonic replay clocks and USD/USDC/fee accounting with amount-dependent fill costs. (4) Freeze reviewed datasets and held-out/warmup schedules, then persist complete experiment/results and restart state before candidate comparisons. [Birdeye terms, opening provisions and section 10.2](https://birdeye.so/data-api/terms-of-service).

**Validation:** all 581 offline worker tests, 75 frontend tests and TypeScript pass. The 38 new tests cover canonical bytes and full-range seeds, safe CLI operation without credentials/site packages/network, size/path/FIFO/symlink bounds, exclusive and failed publication, nested immutability, digest tampering and invalid rehashed payloads, timing/identity/units, candle coverage/gaps/revisions, exact warmup delivery, and generator parameter validity. Real controller tests reproduce identical 501-frame trades/indicators despite changed pacing and unrelated randomness, and all four real optimizers preserve common-window account results and offspring. A fully validated provider-shaped generated test bundle is refused by ReplayFeed; no paid provider data is acquired. EOF exposes no fresh fallback marks. Dataset identity survives JSON persistence in the offline repository recorder. Independent review found and fixed incomplete warmup checks, variance overflow admission, and unbounded directory enumeration.

**Release boundary:** read-only target verification matches GitHub TOOTRJ/TheDashboard / 1141090963, Vercel the-dashboard / prj_wFUe9k9USVreOQcmQKNWRAVsx5fH / team_8iNNxiNjrOseD4gdSCHkQEzF, and Supabase The Dashboard / fxpxsciltakyypunglzr / cqfnnaunmupdyobkyqfo (ACTIVE_HEALTHY). Baseline PR #19 merge 3ac7e8e85440788e01713626162beab579363665 is READY as dpl_JBDRog6Kj5yFPxpLBDydi4gw9pXG. This section's PR records exact source, preview, merge, production and read-only smoke evidence. No migration, live provider collection, worker/colony start, shared credential change, wallet action or other-project edit is required. The worker remains unhosted; a dashboard deployment does not execute it.

## 27. USD reference execution accounting (2026-09-30)

**Scope:** FILL-01A integrates a versioned, immutable percentage-cost scenario into
actual Probe/Genesis operation, persistence and dashboard reporting. The
[execution contract](services/vonneumann/EXECUTION-CONTRACT.md) defines the math,
units, timing, limitations and dated primary research. This is hypothetical USD
reference accounting for simulation/paper observations. It is not USDC settlement,
a calibrated Solana fill simulator or authorization to submit transactions.

Entries spend an all-in budget with explicit acquired quantity, invested notional,
fee and adverse spread/slippage adjustments. Holdings are valued by quantity;
entry fees are excluded from invested principal. Every exit
uses the same validated calculator. Terminal loss is an explicit write-off without
an invented exit fee. Trade JSON preserves reference/fill prices and gross/net
results; event/database P&L is no longer display-rounded. Existing pnl_pct storage
uses percentage points while the internal return remains a fraction.

Completed cohorts now liquidate before scoring, so final fees reduce fitness/ROI
and cash. Costs can trip the account breaker before another queued entry, sibling
probe or replacement birth. Pure preflight and already-applied event preservation
remain intact. Stop/take-profit triggers use reference movement from entry;
execution adjustments affect proceeds, so a triggered take-profit need not produce
a net profit. Cost assumptions are outside the evolvable genes.

The dashboard adds run-level cost controls and a policy notice, a per-trade cost
breakdown, explicit cash versus recorded equity/ROI, and meaningful tiny-price
formatting. Known-version records must reconcile before being displayed as
validated accounting; legacy records remain unclassified. Synthetic/reference
quotes are no longer unconditionally labeled live. Return diagnostics retain the
existing immutable pre-decision sampling policy: final liquidation costs can fall
after the last sample, although net P&L, ROI and fitness include them. Metadata and
the detail view disclose this; FILL-01B tracks a deeper sampling-policy review.

**Independent verification:** 608 offline worker tests pass, including 13 pure
calculator tests and 14 integration tests. Independent Decimal fixtures reconcile
cash/quantity/costs; tests cover invalid numeric/config values, write-offs,
preflight purity, all exit paths, full-precision persistence, immediate risk
precedence, and all four real optimizers over four paid-trade generations.
Original synthetic input and immutable replay produce identical trades, offspring
and final balances; reserve plus active cash reconciles with recorded net P&L.
An existing isolated cash-pooling fixture now uses a 60% breaker limit so its 50%
loss can test pooling rather than the new allocation checkpoint's 30% halt.

**Database plan:** one nullable `vn_trades.execution JSONB` column, no backfill or
existing-row reinterpretation. Target verification again confirmed GitHub
TOOTRJ/TheDashboard (1141090963), Vercel the-dashboard
(prj_wFUe9k9USVreOQcmQKNWRAVsx5fH / team_8iNNxiNjrOseD4gdSCHkQEzF), and Supabase
The Dashboard (fxpxsciltakyypunglzr / cqfnnaunmupdyobkyqfo). Read-only catalog
preflight found thirteen applied migrations and no execution column. The linked
dry run selected only `20260930030000_vonneumann_execution_accounting.sql`.
A task-owned PostgreSQL 17.6 container with no network/ports exercised the exact
migration under lock contention (5.05-second timeout with no schema change), then
successful application, DO-block rollback on injected failure, preservation of
legacy NULL/security, the copied-schema contract, and three exact Python → JSONB
→ Python execution round trips including tiny prices and large finite ratios.
See [migration plan](supabase/MIGRATION-PLAN.md) for release and rollback procedure.

**Research/setup boundaries:** no provider dataset was acquired. Account-specific
retention, combination, backtesting and redistribution rights remain unresolved;
the user has been asked for applicable terms or written permission. Zero-cost
runs are explicitly frictionless mechanics controls, not empirical estimates.
FILL-01 remains open for calibrated impact/latency/rejection/on-chain fees/token
precision/FX. The new JSON is not an atomic ledger or restart checkpoint. The
[next durability plan](services/vonneumann/PERSISTENCE-RECOVERY-PLAN.md) prioritizes
fenced interruption and transactional idempotency before restoration or hosting.
The Python worker remains unhosted. Other projects, shared credentials, Claude
configuration/processes and the user's edited historical migration are preserved.

**Verified migration and frontend checks:** the exact forward migration applied
successfully to The Dashboard only. The ledger now has fourteen versions and the
linked dry run reports no pending migration. Before/after comparison found exactly
one added nullable JSONB column; all captured policies, RLS flags, triggers,
constraints, indexes and prior column definitions are unchanged. The temporary
copied-schema contract passes, and the privileged zero-row PostgREST read of
`vn_trades.execution` returns HTTP 200 with no rows. No application/auth records
were used as fixtures. All 90 frontend tests, TypeScript and the isolated Next.js
production build pass; broad lint reports zero errors and 33 existing warnings.


## 28. Jupiter documentation tooling and historical-data decision (2026-09-30)

The user confirmed Jupiter permits backtesting retention. This supersedes the
outstanding Jupiter-permission question recorded in section 27; separate Birdeye
terms/entitlements remain unresolved. The accepted design is small on-demand
historical OHLCV downloads with immutable experiment snapshots. A 24/7 archive
is deferred. Historical playback still needs explicit availability and execution
assumptions; the current replay implementation remains synthetic-only.

Reverification matched GitHub `TOOTRJ/TheDashboard` / `1141090963`, Vercel
`the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` /
`team_8iNNxiNjrOseD4gdSCHkQEzF`, and Supabase `The Dashboard` /
`fxpxsciltakyypunglzr` / `cqfnnaunmupdyobkyqfo`. Production was READY at merge
`3d0923471be5183f2011920360e2c6fac2d4f594` before this documentation setup.
No database changes, market-data acquisition or account-setting changes were
needed for this setup. Existing user edits and other-agent configuration remain
preserved.

Installed the official `integrating-jupiter` (1.2.0) and `jupiter-swap-migration`
(1.1.0) skills under `.agents/skills`, pinned to upstream commit
`a2211e3f6a7caa03310c7a9a8d816e723b0bdc5f`. Preserved unmodified upstream files,
MIT notices and SHA-256 provenance. Project `.codex/config.toml` connects the
official documentation MCP at `https://developers.jup.ag/docs/mcp`, allowing only
`search_jupiter` and `query_docs_filesystem_jupiter`; feedback submission is not
enabled. Codex resolved this exact configuration. MCP initialize, tools/list,
documentation search and Price V3 OpenAPI retrieval passed without credentials.
Activation in the running client may require reconnect/restart; newly installed
skills are available on a subsequent turn.

The official CLI was source-reviewed and deferred: it initializes shared-home
configuration even for help/version, and its alpha trading surface is unnecessary
for offline research. Trading MCP and unrelated product skills were also deferred.
Current docs override stale skill quota/authentication examples; migration examples
do not authorize their suggested live swap test. No global Codex/Claude, shell,
wallet or package configuration was changed. See [tool setup](JUPITER-TOOLING.md)
and [data research](services/vonneumann/JUPITER-DATA-RESEARCH.md) for decisions,
source links, known ambiguities, verification and next priorities.

## 29. Explicit EMA baseline and quote-only Jupiter V2 (2026-09-30)

BASE-01 adds an opt-in `ema_baseline_v1` profile. Only the two integer EMA periods
evolve; RSI/volume features are disabled, while asset, candle timeframe,
position/exposure and risk controls remain fixed within the experiment. Previous
and current canonical completed-candle EMAs determine true crossings. Every
candidate requires 61 completed bars, including narrowed/control domains, before
the common evaluation horizon starts. Existing causal intents, protective exits,
net liquidation and account risk checks remain in effect. Default/legacy launches
retain their existing signal semantics. [Baseline contract](services/vonneumann/EMA-BASELINE.md).

The dashboard exposes the opt-in preset, its two ranges, one asset and common
horizon, with explicit fixed-control/warmup descriptions. Resolved initial,
runtime and startup-failure metadata carry a versioned signal policy. Saved runs
without evidence remain unclassified. Review found and repaired shared-preset
list aliasing and a clear/retype input case that poisoned a hidden default with
NaN. This section uses existing configuration/runtime JSON, without a migration.

DATA-03A migrates the unused swap helper to V2 `/order` without `taker`. The new
immutable result validates exact atomic integer amounts, pair, slippage and the
quote-only schema. It enforces a five-second total deadline, a 256 KiB
decompressed body limit, redacted local errors, no redirects and one transport
attempt, including aiohttp's internal reconnect behavior. It is not connected to
the fill engine and exposes no signing/broadcast path. Receipt clocks/hash do not
establish source freshness, net wallet accounting or replayable data. Current
official documentation/OpenAPI informed the
[bounded adapter contract](services/vonneumann/JUPITER-SWAP-CONTRACT.md).

**Verification:** 644 offline worker tests and 100 frontend tests pass; TypeScript
and an isolated Next.js 16.3.8 production build pass. Broad lint has zero errors
and 33 existing warnings. Twenty independent baseline tests cover a 70-digit
Decimal EMA oracle, full-precision crossings, zero-volume/RSI-disabled behavior,
fixed warmup, birth/catch-up/receipt causality, protective exits, configuration
isolation, API/repository metadata and all four real optimizers over four
populations. Sixteen quote tests cover request/response constraints and HTTP
failure/retry boundaries. Frontend checks exercise the actual dialog, preset
switching, rejected invalid inputs, selected-run policy and saved metadata.
Independent Python and frontend reviews found no remaining blocking issue.
These are offline mechanics checks, not deployed-worker or performance acceptance.

**Release preflight and rollback:** immediately before publication, identity
checks matched GitHub `TOOTRJ/TheDashboard` / `1141090963`, Vercel `the-dashboard`
/ `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` / `team_8iNNxiNjrOseD4gdSCHkQEzF`, and
Supabase `The Dashboard` / `fxpxsciltakyypunglzr` / `cqfnnaunmupdyobkyqfo`.
The prior production deployment `dpl_GhWtvUHUq19njbgh6Qr7UcasEw7w` is READY at
`4700616b0335ac97ac4f9aff03bc4c8cd10514d8`. Release through a reviewed `codex/`
branch and PR, verify the preview's exact source commit before merging, then
verify the production alias's exact merge commit and read-only authentication/API
smokes. If regression is observed, revert this PR through the same target-checked
workflow; this section has no schema rollback. Record deployment results in the
PR. The Python worker remains unhosted; frontend publication alone does not
deploy its new runtime.

**Remaining priorities:** BASE-02/03 frozen grid and honest controls; DATA-01C
bounded historical acquisition with availability/fill semantics; FILL-01B
calibration; and DB-03A/SVC-02 durable interruption, idempotency and fencing before
hosting. Research EMA initialization sensitivity, out-of-sample/multiple-testing
methods, provider candle revisions/outlier semantics and account-specific Birdeye
entitlements/retention in depth. Jupiter retention is already user-confirmed.
No dataset acquisition, provider quote request, account-setting change, database
write, wallet operation or worker hosting was part of this section. Existing
user changes, other projects and the other agent's credentials/configuration were
preserved.

## 30. Offline EMA grid, controls and replayable result evidence (2026-09-30)

BASE-02A/03A add a standalone synthetic research command, without starting the
worker or connecting providers/database clients. It evaluates twenty declared
EMA pairs plus fixed 9/21, cash and passive 25%/100% buy-and-hold controls. Each
independent account shares data, fixed experiment controls, exact boundaries and
declared costs. It reuses the real Probe signal/protective-exit code and existing
fill calculators, without Genesis capital pooling or candidate replacement.

All candidates require 61 completed timeframe bars; every completed minute must
arrive on its modeled quote frame. Starting boundaries remain cash-only and
terminal boundaries apply protective risk/drawdown death before costed liquidation,
without pending order execution. Early deaths retain cash. A training-only
selection uses versioned net fitness and stable ties, with seeded random-prefix
budgets/cache usage disclosed. Its complete ledger is hashed before holdout.
Holdout resets accounts/positions/intents/risk while preserving only causal
indicator history, and evaluates only selected winners and prespecified controls.
See the [workflow and contract](services/vonneumann/OFFLINE-RESEARCH.md).

Each candidate has a complete ordered per-frame ledger containing indicator
evidence, pending intents, fills and intermediate/post-action equity. Independent
cash/quantity/P&L reconciliation avoids relying on the live probe's trimmed trade
cache. Result identity binds dataset, configuration, policies, source hashes and
Python version. The bounded immutable artifact codec checks canonical finite
JSON, paths, exact files and hashes; exclusive manifest-last publishing never
overwrites another output. CLI `verify` goes further and reproduces every payload
field from the bound dataset, rejecting rehashed numerical tampering.

**Verification:** all 684 offline worker tests pass, including 40 new tests
(15 runner, 16 artifact, 9 command-line). Independent fixtures prove Decimal
buy-and-hold costs, frame/event equity and drawdown, unchanged training under
holdout-only edits, warmup/coverage/terminal timing, dead cash and cooperative
cancellation. Fresh command-line child processes use minimal environments,
deny network/live-client/environment-loader imports, and reproduce identical
bytes under different Python hash seeds. Tests cover semantic tampering,
missing/extra files, symlinks, nonfinite values, size/depth limits, interrupted
publication and preservation of existing outputs. Independent review found and
fixed two new evaluator edges: trailing missing candles could appear successful,
and terminal-only drawdown previously missed the death lifecycle.

A full default-size smoke used 3,795 synthetic one-minute frames, seed 42,
15-minute candles, 1,440-minute train/holdout windows, and hypothetical
5/5/10-bps fee/half-spread/slippage. It produced 24 training accounts, five
deduplicated holdout accounts, 41,789 ledger rows and 42 closed trades in an
11,362,060-byte payload. A separate command fully reproduced it:
dataset `0686b0dd5fdbad56cf9ac1b2ccef704375385d615955ea88d8fe2f7f8a9a50e9`,
result `00e300008cde8c11f78b19049c08c196a70c167338f8e6bb8d3528efb797e020`.
These figures are mechanics evidence, not historical-performance results.

**Target/release preflight:** matched GitHub `TOOTRJ/TheDashboard` / `1141090963`,
Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` /
`team_8iNNxiNjrOseD4gdSCHkQEzF`, and Supabase `The Dashboard` /
`fxpxsciltakyypunglzr` / `cqfnnaunmupdyobkyqfo`. The existing READY production
deployment is `dpl_C7uaeBB2h81YPBC6rrCJ57ugf33A`, merge
`e4e35bc3d52fb9ed9eecca4ffb93590a3040fbd5`. Release on `codex/` through a PR,
verify its exact source preview, then verify the production alias's merge commit
and read-only authentication/API smokes. Record results in the PR. A reviewed
revert restores code if needed; no schema rollback is involved. This section
changes neither frontend runtime nor database schema, and does not host a worker.
User migration edits, other projects, shared credentials and Claude configuration
remain excluded from commits and operations.

**Open gates:** BASE-02/03 remain open for historical acceptance and equal-budget
GA comparison. DATA-01C/FILL-01B must establish provider availability/provenance
and execution assumptions. Research longer-prehistory sensitivity, sample/regime
adequacy, correlated trials, holdout reuse and objective selection before
economic claims. The 10,000-frame fixture cap is not adequate-sample evidence;
larger datasets need streaming ledgers and measured memory limits. DB-03A/SVC-02
still gate unattended hosting; this local result bundle is not worker recovery,
a transactional database event ledger or writer fencing. No provider dataset,
API key, migration, wallet action or live trading was changed or initiated.

## 31. Equal-budget reference GA comparison and next worker prerequisites (2026-09-30)

BASE-03B adds a deliberately small discrete reference GA to the existing offline
EMA evaluator. Random search and GA share the twenty-point domain, training
objective, first four seeded candidates and exact logical request budget. The
GA has a fixed four-member population, binary tournaments, uniform crossover,
0.25 mutation probability per locus and one elite plus three requested children.
Duplicates consume requests; copied elites are separately counted reuse. Partial
generations can improve best-seen fitness without changing their parent pool or
exceeding the budget. These are declared mechanics settings, not tuned trading
parameters. The deployed worker's production optimizer is unchanged.

Each selector sees only requested finite, stationary scalar training fitness.
The runner adds oracle regret, optimum-fitness/canonical-winner hits and the
paired fitness difference only after both searches finish. This distinguishes
fitness ties from candidate identity. Search traces stop at the chosen budget;
the random permutation's remaining order is metadata only. All training scores
come from the separate twenty-grid/four-control benchmark: every request is a
cache read, with zero additional market replay and no claimed runtime saving.
The deduplicated GA/random/grid winners and fixed controls get fresh holdout
accounts. No holdout ranking or parameter adjustment occurs.

Engine version is `ema-grid-mechanics-v2`, including the new search module's
source hash. The generic artifact envelope and strict config shape remain
version 1. Existing `random_seed`/`random_budget` fields govern both algorithms;
CLI help explains this. Old artifacts remain readable but require their original
source/runtime for full replay. See [the contract and current primary research](services/vonneumann/OFFLINE-RESEARCH.md).

**Verification:** all **703 worker tests pass** (19 new tests: 16 search, two
runner and one CLI), plus the strengthened enormous-integer fitness validation
case. The independent search suite checks budgets 1–20, shared initialization,
prefix consistency, duplicate charges, partial-generation parent eligibility,
mutation threshold and best-seen/tie behavior. Making an unvisited candidate
uniquely optimal leaves the GA trace unchanged, while exhaustive random coverage
finds it. Existing holdout-suffix, accounting and fresh-process offline checks
continue to pass. Rehashed search/diagnostic tampering fails full CLI replay.
A separate read-only review exercised 800 seed/algorithm/budget cases without
finding a budget or ranking defect. No frontend runtime or dependency changed;
the exact automatic Vercel builds remain release checks.

The prespecified default smoke reuses the 3,795-frame seed-42 synthetic fixture,
15-minute candles, 1,440-minute train/holdout windows, search seed 0/budget 10 and
hypothetical 5/5/10-bps fee/half-spread/slippage. It produces 24 training accounts,
six deduplicated holdout accounts, **43,230 ledger rows**, 47 closed trades and an
11,777,190-byte result. A separate CLI verification reproduced the whole payload:
dataset `0686b0dd5fdbad56cf9ac1b2ccef704375385d615955ea88d8fe2f7f8a9a50e9`,
result `c080d682eb6547b410d2cab25a2ca0d9a7a0b469203b0e7716849f1dc3cdd809`.
Random visited ten unique pairs and selected the grid optimum `ema-08-30`.
GA visited six unique pairs plus four duplicates and selected `ema-03-20`, with
training fitness lower by approximately 0.0200088 objective units. This is one
synthetic mechanics outcome, not a superiority or historical-profitability test.
No seed/settings were changed to improve that result.

**Next prerequisites:** SVC-02A admission/startup tracking/drain is the next local
batch; then DB-03A needs real isolated PostgreSQL tests and a complete fenced
write cutover. The read-only review confirmed in-memory-only ownership, separate
economic writes, untracked preparation during drain, retained controller growth
and an empty repository config cache that cannot safely rewrite old-run details.
A lease-only patch cannot protect paths that still write directly. DATA-01C can
prepare importer/provenance fixtures now; actual acquisition needs the separate
Birdeye rights/entitlements and a concrete shared-credit budget. Jupiter retention
permission remains accepted. Paired multi-seed, historical availability/cost,
initialization bias and production-solver adapter research remain explicit open
tasks before adding genes or claiming an economic result.

**Verified release targets:** GitHub `TOOTRJ/TheDashboard` / `1141090963`;
Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` /
team `team_8iNNxiNjrOseD4gdSCHkQEzF`; Supabase `The Dashboard` /
`fxpxsciltakyypunglzr` / organization `cqfnnaunmupdyobkyqfo`, ACTIVE_HEALTHY.
The current READY production rollback point is `dpl_G5ygYM6s5yCENuD4kGskSb8fhtPv`,
merge `2e7eaf719d945ceb83362995e7dfea33caaf90f2`. Publish a `codex/` PR, verify
the exact source preview, merge the checked head, then verify the production
alias's exact merge SHA and four read-only authentication/API smokes. Record
actual deployment evidence in the PR. A reviewed revert restores code; no
schema rollback is involved. Existing migration edits, Claude configuration,
other projects and shared credentials are excluded. No provider acquisition,
database write, hosted worker, wallet action or live trading is part of this release.

## 32. Worker admission, tracked startup and truthful draining (2026-09-30)

SVC-02A fixes an initial-insert/shutdown race: a start was invisible to the manager
until its first write completed, so a late acknowledgement could launch after
shutdown's snapshot. Both HTTP routes now reserve a manager-owned task before
repository construction, retaining it through insert acknowledgement, preparation
and compensation. Direct manager creation shares the same gate; duplicate IDs
cannot overwrite task/controller/lock state. The default limit is 32 retained
colonies, including starting/stopped/failed entries, without eviction. Constructor
overrides are bounded integers 1–128; no new environment setting is required.

Shutdown closes admission before awaiting, tracks accepted controls and sets a
monotonic Genesis drain flag. Accepted batches can finish, but a pending resume
or risk-recovery acknowledgement cannot enable another tick batch. One owned
shutdown task and its original 40-second deadline are reused. Waiting returns
pending work without cancelling it or freeing database write ownership. Each
colony has one retained resource-close attempt; local cleanup waits can expire
without losing that attempt or starting a second close. Failed cleanup or an
unacknowledged required terminal write prevents a complete report even after
all tasks finish. Lifespan cleanup runs in `finally` and raises a safe error on
incomplete drain instead of logging success.

An unacknowledged initial insert is retained as an owner-visible failure. Its
compensating update changes status without supplying runtime details from an
empty repository config cache, preserving a potentially committed configuration.
No insert is retried. Acknowledged compensation and failed compensation have
different persistence flags; positions/cash are retained without manufactured
fills, death/reproduction scores or reserve credits.

Public health remains the fixed liveness response. A new authenticated readiness
route returns HTTP 503 with local admission and durable recovery unavailable,
without owner IDs, run IDs, counts, limits or provider diagnostics. Only exact
pre-admission 503 responses identify a launch as rejected before startup. The
dashboard uses known local messages for those responses; all ambiguous or
already-accepted failures retain uncertain-outcome guidance and never auto-retry.
See [the lifecycle contract](services/vonneumann/WORKER-LIFECYCLE.md) for schemas,
deadlines, primary asyncio/FastAPI references and remaining research.

**Validation:** all **734 offline worker tests** and **103 frontend tests** pass.
The 31 new worker tests comprise 16 admission/drain cases, ten HTTP/lifespan
cases and five lifecycle regressions. They cover last-slot races, duplicate
identities, initial/running acknowledgements crossing drain, cancellation-resistant
preparation, repeated caller cancellation, real risk-recovery publication while
draining, slow/failed resource closure, retained positions, and lost insert ACKs
through the real repository with fake database I/O. Existing repository tests
still prove write locks remain held through repeated cancellation. Independent
review additionally cancelled successive shutdown callers while cleanup was
blocked, confirming one drain/deadline and one startup cancellation. TypeScript
and the isolated Next production build pass; broad lint has zero errors and
33 pre-existing warnings. The build uses a temporary copy and fake credentials,
without local environment files. No live worker, provider or database was used
by the tests.

**Next gate:** DB-03A must implement and rehearse database-time leases/fencing,
idempotent journal/revisions, atomic economic boundaries and direct-write bypass
restrictions against isolated real PostgreSQL before any target migration.
Process-local drain is not recovery or multi-worker coordination. A host can
still terminate pending work; no checkpoint restores it. Measure memory at the
retained bound, shutdown/acknowledgement tails, transport timeouts and deployment
grace periods before hosting. Shared paper polling/quota scheduling and historical
data/production-solver acceptance remain open. Do not clear retained uncertainty
by advising an unreviewed restart or increase limits to mask capacity issues.

**Release targets and rollback:** reverified GitHub `TOOTRJ/TheDashboard` /
`1141090963`; Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` /
team `team_8iNNxiNjrOseD4gdSCHkQEzF`; Supabase `The Dashboard` /
`fxpxsciltakyypunglzr` / organization `cqfnnaunmupdyobkyqfo`, ACTIVE_HEALTHY.
Existing READY production is `dpl_5Roe5Xfwfpp5uz13NdfxXa1Wrcro`, commit
`f58381f0f02ea89f295e4b0d207c76b25bc45e10`. Publish a `codex/` PR, verify its
exact source preview before merging, then verify production's merge SHA and
the four read-only login/authentication/zero-row API smokes. Record actual
deployment evidence in the PR. A reviewed revert restores code; no schema or
environment rollback is involved. The frontend formatter is deployable through
Vercel; Python source remains unhosted. Supabase schema/data/credentials, user
migration edits, Claude configuration, shared tooling and other projects are
unchanged. Live signing, funding, swaps and trading remain outside this release.

## 33. Isolated database ownership and transaction rehearsal (2026-09-30)

**Scope:** DB-03A1 implements an executable design contract in
`services/vonneumann/db-contract/001_fenced_commands.sql`, outside Supabase's
migration directory. No production runtime imports it. The fixture schema is
`vn_durability` in a newly initialized disposable PostgreSQL cluster; existing
`public.vn_*` projections and their write paths are unchanged. DB-03A, DB-02,
full restart restoration, and worker hosting remain open.

**Database boundary:** creation atomically records initial reserve, worker UUID,
fence, database-time lease and command revision. Heartbeats and commands lock
the run before checking `clock_timestamp()`; expired ownership cannot renew.
Typed bounded batches atomically debit/credit reserve and account cash, open or
close positions, retire accounts and change lifecycle while recording one
immutable request/result/hash at a unique revision. Later operation failure
rolls back the whole batch. A partial unique index permits only one open
position per account/asset. Risk halts cannot be cleared or routed through pause;
the rehearsal has no recovery operation without ENG-05 trip/freshness evidence.

Exact decimal strings and PostgreSQL numeric avoid float serialization and
silent rounding in these fixtures. The finite 10^36/36-decimal-place bounds,
256-operation batch cap and 30-second lease are provisional contract parameters,
not calibrated market or hosting recommendations. Server-side SHA-256 binds the
PostgreSQL JSONB request text, including owner/run/command identities and applicable
worker/fence/revision. Full request comparison rejects changed-ID reuse semantics;
JSON key order/whitespace normalize, but decimal string spelling remains exact.
A versioned engine serializer and precision policy are still required.

Stable-ID read-only resolution remains available after lease loss. An absent
journal entry while a request is in flight is explicitly inconclusive. Interruption
advances the fence/revision and records `worker_interrupted` without changing
configuration, reserve, accounts or positions. It does not resume, liquidate,
reclaim capital or submit interrupted fitness. The journal supplies ordered
committed evidence; WebSocket replay/deduplication is not yet implemented.

**Isolation and security:** an opt-in runner pins the existing PostgreSQL 17.6
image to its immutable local image ID and pins the local Docker Unix socket.
Each test class uses a uniquely labeled container with no network, ports, host
mounts or application credentials, a read-only image and bounded tmpfs/resources.
`fsync` remains on. Actual independent anon/authenticated/service-role connections
exercise RLS and object permissions; service_role has BYPASSRLS but no direct DML.
Only explicit RPCs execute with a dedicated NOLOGIN owner's privileges. Fixed
search paths, qualified objects and private helper grants prevent tested bypasses.
The runner removes only its own exact labeled containers. Temporary storage and
backend termination do not establish power-loss or production host durability.

**Review findings repaired:** real close/retire tests exposed an invalid
PL/pgSQL local-variable qualification; the close branch now uses an unambiguous
name. Independent review demonstrated that a schema-only default EXECUTE revoke
cannot remove the global PUBLIC default. The dedicated fixture owner's defaults
now revoke PUBLIC execution globally, with a regression for later-created helpers.
Current function grants are also explicitly revoked in the installation transaction.
A separate installation marker prevents accidental manual execution; it confers
no privilege and is not relied on for security. See the official
[PostgreSQL privilege explanation](https://www.postgresql.org/docs/17/sql-alterdefaultprivileges.html)
and [contract research references](services/vonneumann/db-contract/README.md).

**Validation:** all 734 existing worker cases pass. Normal discovery also skips
the six opt-in harness cases and the contract class without starting Docker.
The separate explicit PostgreSQL runner passes all **41 cases** (35 contract,
six harness) in 50.461 seconds, including simultaneous independent sessions,
after-lock/in-write expiry, uncertainty readback, replacement rollback, actual
backend termination, numeric overflow/NULL boundaries, risk-halt bypass rejection,
duplicate-position protection, RLS and helper/search-path permissions. Independent
review and temporary-container probes found no remaining blocking issue within
the documented rehearsal scope. Application TypeScript, frontend code and
dependencies are unchanged; this batch does not claim a new browser/worker
integration test or Supabase migration rehearsal against the legacy schema.

**Next implementation order:** DB-03A2 must prepare complete engine economic
plans before mutating local state, integrate command resolution and committed
responses, persist the real genome/cohort/risk/evaluation/generation metadata,
and prepare exact-object privilege and browser archive changes together. DB-03A3
then validates that entire cutover against the actual legacy schema and client
roles before any forward cloud migration. Research numeric/engine interoperability,
lease timing under real latency, role inheritance/custom worker credentials,
legacy classification, journal retention/pagination and checkpoint compatibility.
The existing browser `deleteAllProbes` direct-write path must not survive the
cutover. A lease-only patch would not satisfy the acceptance criteria.

**Release targets and rollback:** fresh read-only metadata verifies GitHub
`TOOTRJ/TheDashboard` (`1141090963`); Vercel `the-dashboard`
(`prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`) in team
`team_8iNNxiNjrOseD4gdSCHkQEzF` / `orderoftheredjester`; and Supabase
`The Dashboard` (`fxpxsciltakyypunglzr`) in organization
`cqfnnaunmupdyobkyqfo` / `Valentine Jester`, ACTIVE_HEALTHY. Both local project pins
match. Existing READY production is `dpl_FhwBv5i1433wXz9yDwQoPYcMUoyj` on
`6c0f4d1d8e86e4b4f5719f727be45c60e391a220`. Publish a reviewed codex branch PR,
verify its exact source preview, merge the tested head and verify the production
merge/alias plus four read-only authentication/API smokes. Record actual deployment
evidence in that PR. Rollback is an ordinary reviewed code revert; this release
has no cloud schema, environment or data changes to undo.

The current Vercel CLI reports 62.0.0; help was inspected and the dedicated profile
and verified scope remain in use. No explicit CLI upgrade or shared-tool
configuration change was performed. The user's edited historical colony migration retains SHA-256
`a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc` and is excluded
from the release. Claude configuration, shared credentials/processes and other
projects are preserved. No worker, market acquisition, wallet operation or live
trading is started by this release.

**Publication checkpoint:** source commit
`3556958ab6680b5c3b9b59d769f3135dd94ce3e3` is local on
`codex/database-contract-rehearsal`, with verified biggrizzly11 author/committer.
Before push, a repeated target verification failed in Vercel CLI's local runtime
(`err` out of range). The existing Node 24 runtime also stalled; only that
confirmed task-owned verification child was stopped. Inspection of the installed
CLI confirmed that Keychain accounts are scoped by the global-config auth path.
The exact Dashboard credential file was absent and the corresponding Dashboard
Keychain item returned not found. No shared credential was read or changed.
Publication/merge was held pending a Dashboard-only sign-in and fresh verification.
The user was given the exact dedicated-profile login command.

The dedicated profile also has automatic CLI updates enabled. Subsequent Dashboard
CLI commands must set `NO_UPDATE_NOTIFIER=1` per child to prevent global update
checks, and `VERCEL_TOKEN_STORAGE=file` to use only that profile's private file.
No shared configuration is edited to accomplish either change. The cause of the
missing authentication and previously observed CLI version change is not established.
Do not assume a successful earlier identity check proves current release access.

**Access restored (2026-10-01):** after the user's dedicated-profile sign-in,
fresh GitHub, Vercel and Supabase metadata again matched all three allowlisted
project identities and owners. Vercel CLI reads succeed with per-command
`NO_UPDATE_NOTIFIER=1` and `VERCEL_TOKEN_STORAGE=file`; no shared profile or
credential fallback is needed. The release access hold is cleared. The tested
SQL and Python files are unchanged; publish through the reviewed branch and
record exact preview/merge/production smoke evidence in the PR. This restores
release access only; the database contract remains an isolated rehearsal and
no Supabase migration or hosted worker is included.

## 34. Immutable worker commands and uncertainty rehearsal (2026-10-01)

**Scope:** DB-03A2A adds `db/command_protocol.py` and
`db/command_repository.py`, with fast tests and an adapter-to-PostgreSQL fixture
suite. The modules accept only explicit inputs/injected transport. They load no
credentials or application connection and are not imported by the running
worker. Existing CRUD persistence, browser writes, SQL fixture, migrations,
frontend, dependencies and readiness behavior are unchanged.

**Implemented:** prepared commands bind stable canonical UUIDs, exact operation
keys, integer fences/revisions and immutable request bytes. Economic amounts
must be decimal strings; all float JSON/config values are rejected rather than
silently converted. Returned dictionaries/receipt data are copies. Each run has
one owned RPC and one unresolved command. Caller cancellation cannot discard an
admitted request; a matching late reply remains available as `last_receipt`.
Failed/malformed replies retain the original command and freeze new submission.
Read-only resolution validates the complete typed request and result; absent
journal evidence remains uncertain and never authorizes another write ID.
The PostgreSQL request hash is format-checked, not falsely recomputed using a
different JSON encoding.

Creation replay never grants a decision lease. A matching heartbeat uses local
request-start monotonic time less a safety margin; delayed or invalid replies
leave the lease unavailable. Closed admission stays closed through later
acknowledgment, while original-command readback remains available. Terminal
interruption preserves configuration, balances and positions. The adapter has
no restart-adoption, economic retry, candidate installation or outbox-delivery
API. Those remain full-cutover requirements.

**Findings driving next priorities:** independently encoding the current float
fill's notional and fee can exceed its stated cash debit (100 becomes
100.00000000000000734). A versioned arithmetic/residual/rounding policy is needed
before engine-to-ledger integration. CMA records whole-distribution lineage,
which cannot fit the rehearsal's two-parent birth contract without losing
evidence. Preserve distribution sources and template/genetic ancestry
separately. Whole-controller deep copy fails on immutable candle mapping proxies
and would improperly mix locks/feeds/drain latches with candidate state. Plan
data-only engine/optimizer/RNG transitions before submission and install only
the matching committed candidate before publication or another decision.

Independent review also found mutable repository identity attributes and JSON
serialization coercing tuples/non-string keys during journal comparison. Both
are repaired with read-only identity properties and strict recursive protocol
JSON validation. Regression coverage includes Python 3.12 eager task scheduling,
scheduler failure, cancellation before execution, caller cancellation, late
acknowledgments, closed admission, invalid clocks and cross-event-loop use.

**Validation:** 789 ordinary worker tests pass (734 existing, 15 protocol, 40
repository). Normal discovery reports 795 run and eight skips: six opt-in
harness tests plus two class-level PostgreSQL skips. The separate explicit
PostgreSQL runner verifies 46 cases (35 SQL contract, six harness, five new
adapter cases). The latter cover exact decimal accounting, lost create/batch
replies, read-only resolution after expiry, late full-batch rollback and
interruption preserving an open position. These tests use only temporary
no-network harness containers and fake identities. No production PostgREST,
legacy-schema or engine-to-UI acceptance is implied. No new frontend test/build
run is claimed for this Python-only batch; exact Vercel Git deployment status
is checked separately during release.

**Verified release scope and rollback:** GitHub `TOOTRJ/TheDashboard`
(`1141090963`); Vercel `the-dashboard` (`prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`), team
`team_8iNNxiNjrOseD4gdSCHkQEzF` / `orderoftheredjester`; Supabase `The Dashboard`
(`fxpxsciltakyypunglzr`), organization `cqfnnaunmupdyobkyqfo` / `Valentine Jester`,
ACTIVE_HEALTHY. Both local pins match. PR27 is merged at
`6075609272579bb2600a85f94cee30b70f15c6f3`, with READY production
`dpl_MVfiJfHJ7hZuvcLfbKV8T3G9kjA8`; this is the pre-release rollback target.
Publish the reviewed codex branch, verify exact source preview, merge that head,
then verify exact production merge/alias and four read-only authentication/API
smokes. Record actual release evidence in the PR. An ordinary reviewed code
revert is sufficient; this release changes no cloud schema, environment or data.
The user's historical colony-migration edit retains SHA-256
`a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc` and is excluded.
Other-project credentials, configuration and processes remain untouched.

**Remaining gate:** DB-03A2B accounting/lineage, DB-03A2C full engine transitions,
DB-03A2D target-specific inventory/transport/migration/archive plan, then DB-03A3
complete cutover acceptance. Deeper research is required on numeric units,
PostgREST transaction-end/schema/JWT behavior, lease timing including host pause
and clock behavior, role inheritance, journal retention/replay and versioned
optimizer/checkpoint compatibility. DB-03A, durable readiness and hosting remain
open. No worker, provider acquisition, wallet operation or live trading starts.

## 35. Exact accounting and normalized optimizer lineage (DB-03A2B, 2026-10-01)

**Scope:** added pure `usd-reference-decimal-v2` entry/exit plans, bounded cash
calculations, v2 operation builders, typed optimizer ancestry and an extension of
the isolated database rehearsal. No application engine, production transport,
frontend behavior, dependencies or Supabase migration is changed. The current
worker and offline research runner retain their existing v1 execution model.

The new policy uses integer arithmetic with cash at 36 decimal places,
price/quantity at 18 and basis-point settings at six. Buy prices and fees round
up; sell prices and quantities round down. Every unspent budget unit remains
cash. Canonical decimal-string evidence retains its original budget and is
recomputed independently by Python and PostgreSQL. Closes bind to their stored
entry, and a run's immutable policy/version prevents a v1 command from bypassing
the new checks. Zero-credit positive-price fills remain distinct from explicit
writeoffs. Bounds are checked before state installation. This is a provisional
USD-reference research policy, not mint-specific settlement or calibrated fills.

Lineage preserves GA genetic parents, DE target/base/difference sources, PSO
particle/social inputs and CMA's complete ordered distribution membership. CMA
membership is stored once per proposal, with children separately identifying
their asset template. Completion order cannot change the original evaluation
slot binding. Direct SQL rejects duplicate offspring slots, foreign owner/run
sources and malformed identities. A prior distribution reference records
provenance; it does not prove the optimizer checkpoint that produced an update.

The representative normalized 100-member CMA replacement is 201 operations and
57,829 bytes, inside the v2 limit of 1,024 operations and 262,144 bytes. That
measurement excludes position evidence, genomes, metrics and checkpoints.
DB-03A2C must bound the complete transition and reject oversize plans without
truncating ancestry or splitting an atomic economic replacement.

**Validation:** 858 ordinary worker tests pass, including 69 new tests across
exact execution, economic builders, repository version binding, typed lineage
and real 100-member GA/DE/PSO/CMA outputs. Normal discovery reports 864 tests and
nine skips: six explicitly opt-in harness tests and three class-level PostgreSQL
skips. Independent arithmetic checks use 120 rational-oracle cases and hostile
Decimal contexts. Real-strategy tests include reversed callbacks, sorted JSON
metadata, a second CMA generation and swapped evaluation identities. The
separate PostgreSQL runner passes all 59 cases (46 existing and 13 new), covering
real roles, rollback, canonical UUIDs, version/evidence tampering, minimum/maximum
values, residuals and full CMA source membership. Release evidence is recorded
in the PR. Tests use only
disposable isolated local containers and fake identities. No new frontend test
run is claimed for this worker-contract batch; the exact Vercel Git deployments
are verified separately during release.

**Verified targets and rollback:** GitHub `TOOTRJ/TheDashboard` (`1141090963`);
Vercel `the-dashboard` (`prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`), team
`team_8iNNxiNjrOseD4gdSCHkQEzF` / `orderoftheredjester`; Supabase `The Dashboard`
(`fxpxsciltakyypunglzr`), organization `cqfnnaunmupdyobkyqfo` / `Valentine Jester`,
ACTIVE_HEALTHY. Local project pins and the canonical GitHub origin match.
PR28 merge `d2ff15ab854cb45a1dcfb333897864e5935acb0e`, with READY production
`dpl_9LYUoSqLgjy4j3yArJX1WqFHN8rA`, is the pre-release rollback baseline.
Verify the exact source preview before merging, then the production merge/alias
and four read-only authentication/API smokes. Record actual release evidence in
the PR. A reviewed code revert is sufficient; no cloud schema, environment or
data rollback is required. The historical colony-migration edit retains SHA-256
`a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc` and is excluded.
Other-project credentials, settings, tools and processes are preserved.

**Next priority and deeper research:** DB-03A2C must stage complete economic,
cohort, optimizer and RNG state before submission, install only the matching
acknowledgment and retain uncertain candidates without another decision or
optimizer tell. Research exact provider-value decoding, signal/fitness
conversion, rounding impact over realistic ranges, checkpoint compatibility,
distribution-state provenance and complete transition size. DB-03A2D then
prepares the exact target's legacy inventory, production transport, grants,
historical readback and archive/cutover plan; DB-03A3 proves the full flow before
applying it. DB-03A2, durable readiness, restoration and hosting remain open.

## 36. Explicit engine-state and optimizer forks (DB-03A2C1, 2026-10-01)

**Scope:** the first state-isolation prerequisite of DB-03A2C. Added a sealed
in-process engine snapshot with defensive data forks, raw Probe data/candle
forks and explicit GA/DE/PSO/CMA/evaluation forks. No existing controller,
execution, API, UI, dependency or production persistence behavior is changed.
There is no database migration or worker deployment. C2/C3 retain complete
transition planning, atomic state/events, acknowledgment installation and outbox
delivery; the parent C remains open.

The capture acquires the existing tick/recovery lock and copies synchronously,
rejecting incomplete startup and unsupported state. It excludes network/feed
resources, callbacks, bound clocks, operational drain/run/ack flags and identity
allocation. Raw copying preserves retained trade counters, optional offspring
flags, signal intents/cursors, shared recursive EMA state, candidate bindings
and risk/generation data without calling reporting methods or constructors.
`fork()` returns a new independent graph; the snapshot has no execution,
installation, serialization or database authority.

**Confirmed findings:** the installed cmaes 0.13.1 serialization hooks omit the
RNG and recreate it unseeded; ordinary deepcopy is therefore unsuitable for
deterministic solver continuation. The new version-pinned copier bypasses those
hooks and preserves exact RNG state/caches and reviewed solver arrays/mappings.
Independent review also fixed a temporary-dictionary ID-reuse bug in copy
memoization, mutable Gaussian-cache and numeric-array-metadata alias bypasses,
and custom comparison hooks in rejected identity values. Unknown object fields,
resource-bearing state, solver versions and overlapping array views fail closed.

**Validation:** all 902 ordinary worker tests pass. Discovery reports 908 tests
and nine skips (six opt-in harness cases and three PostgreSQL class-level skips).
New coverage comprises 18 controller-state tests, 12 probe/candle component tests and
14 optimizer/evaluation tests. It includes four real solver generations, actual
controllers for all four algorithms across three population replacements,
partial evaluations, cancellation while waiting for the lock, source/sibling
isolation, frozen-record nested mutation, 100 distinct probe captures, retained
terminal capital and forbidden-resource/serialization checks. The SQL fixture
and command protocol are unchanged; the previous 59-case PostgreSQL acceptance
is not represented as rerun for this batch. Frontend tests likewise are not
rerun for these disconnected Python helpers; exact Vercel Git builds and
read-only production smokes remain release checks.

**Capacity and deeper research:** a synthetic 100-member, three-position CMA
replacement has 501 operations and measures 232,899 bytes with simple values,
or 390,099 with fractional price/cost evidence. The latter exceeds the current
262,144-byte cap before state/events. Four/eight-position stress fixtures are
outside the current per-probe asset limit and are not runtime acceptance.
Research a bounded complete-state codec, numerical conversions and fork/commit
memory/latency before raising limits. Preserve valid protective closes when a
later quote/history or decision phase fails. Stage replacement atomically and
never truncate evidence or split economic state to evade bounds.

**Verified target/release plan:** GitHub `TOOTRJ/TheDashboard` (`1141090963`);
Vercel `the-dashboard` (`prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`), team
`team_8iNNxiNjrOseD4gdSCHkQEzF` / `orderoftheredjester`; Supabase `The Dashboard`
(`fxpxsciltakyypunglzr`), organization `cqfnnaunmupdyobkyqfo` / `Valentine Jester`,
ACTIVE_HEALTHY. Canonical origin and both local pins match. PR29 merge
`d42be517d65c94b461826839470bda364272682c`, READY production
`dpl_E38p8R6HeTXdrSCZ3aeZRmHLSaj5`, is the rollback baseline. Verify the exact
source preview before merging and the exact production merge/alias afterward;
record deployment IDs and four read-only smoke results in the PR. A reviewed
code revert is sufficient; there is no cloud schema/environment/data rollback.
The historical migration edit retains SHA-256
`a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc` and is excluded.
Other projects, shared credentials/tools and unrelated local files are preserved.

## 37. Explicit engine decision sources (DB-03A2C2A, 2026-10-01)

**Scope:** the actual controller and Probe now accept explicit event/wall/
monotonic clocks and identity/name sources. Production callers retain dynamic
defaults. Immutable `DecisionInputs` supplies bounded preallocated identities
and generation/name pairs through independently repeatable cursors. It neither
allocates replacements on exhaustion nor touches global name/random state.
Callbacks are operational resources excluded from engine/probe data snapshots.

This completes the nondeterministic-input prerequisite of C2, not full exact
transition planning. Input records contain no market evidence, owner/run/base
revision proof, exact accounts, semantic entity bindings or database authority.
The worker still uses its existing accounting and persistence paths. No SQL,
provider, dependency, API schema or environment change is included; no worker
hosting or live trading is enabled.

**Runtime fixes:** a failed clock read during paper signal discovery no longer
consumes its candle cursor or replaces the pending signal. A failed time,
identity or price dependency before a fill preserves its eligible pending
intent and pre-fill economic state. Successful or deliberately declined fills
consume the intent once. Invalid/duplicate retained generated IDs fail before
funding or trade debits; global/historical uniqueness still belongs to the
allocation source and future durable ledger. Whole-tick rollback is not claimed.
The account-loss latch stays closed if risk identity allocation fails; the
exception propagates to the supervisor's failed/reconciliation path, rather
than representing a successfully persisted or recoverable trip.

**Freshness:** paper quote validation and age budgets sample explicit wall/
monotonic callbacks again at each consumption boundary after awaited work.
Default helpers retain real clock reads. A frozen decision cursor has no lease
or later quote-admission authority. The future coordinator must verify current
source freshness independently of its frozen planning inputs.

**Validation:** all 930 ordinary worker tests pass, including 28 new tests
(10 input-budget, 10 Probe-source and eight controller-source cases). Discovery
reports 936 tests in 27.918 seconds and nine skips: six opt-in PostgreSQL cases
and three PostgreSQL class-level skips. The complete new controller trace uses
the existing two-gene EMA profile and all four actual solvers across three
replacement windows, with real ordinary entries/exits and risk trips. Complete
unnormalized events, identities, names, timestamps, populations, trades and
status match whether publication callbacks return immediately or yield.
Further tests cover paper receipt ordering, stale quotes after awaited close/
price publication, wall-clock rollback, source exhaustion, signal retention,
snapshot resource exclusion and unchanged global random state. Independent
implementation review found no remaining blockers within this declared scope.
The unchanged SQL contract's prior PostgreSQL acceptance was not rerun; frontend
tests were not rerun for these Python-only changes. Exact Vercel Git builds and
read-only production authentication/API smokes remain release checks.

**Next priority and research:** C2B should begin from a new flat exact-policy
run with the two-gene EMA profile, eight members and one asset. Exercise funding,
causal entry, protective/signal closes and full solver replacement through the
isolated SQL contract. Reject implicit legacy float-position adoption. Research
bounded original numeric-lexeme decoding, precision-grid policy, exact trigger
thresholds, indicator/fitness conversion, full state/event encoding, worst-case
payload bounds, peak memory and transaction latency. The current v2 SQL journal
does not bind close reason, source/threshold evidence, cursors or complete
state/events; a reviewed versioned extension remains necessary. C2/C3, the
production cutover, restoration and unattended hosting remain open. Details and
primary sources are in the recovery plan's C2A section.

**Verified target/release plan:** GitHub `TOOTRJ/TheDashboard` (`1141090963`);
Vercel `the-dashboard` (`prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`), team
`team_8iNNxiNjrOseD4gdSCHkQEzF` / `orderoftheredjester`; Supabase `The Dashboard`
(`fxpxsciltakyypunglzr`), organization `cqfnnaunmupdyobkyqfo` / `Valentine Jester`,
ACTIVE_HEALTHY. Canonical origin and both local project pins match. PR30 merge
`df002fc5af6b62661da01f4c1696902db4a5f2e6`, READY production
`dpl_CxVYzDjnvKy6o423T4yMLBz6Uf9r`, is the rollback baseline. Reverify target
identity and the exact source preview before merging; verify production's exact
merge/alias and four read-only smokes afterward. Record release evidence in the
PR. A reviewed code revert is sufficient; no cloud schema/environment/data
rollback is needed. The historical migration edit retains SHA-256
`a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc` and is excluded.
Other projects, shared credentials/settings/tools and unrelated local files
are preserved.

## 38. Bounded exact engine/database rehearsal (DB-03A2C2B, 2026-10-02)

**Scope:** a new flat synthetic run combines the reviewed two-gene EMA profile,
eight members, one asset and three complete replacement windows with all four
actual optimizers. Pure candidates retain detached state and optimizer/cohort
forks. Canonical decimal inputs drive exact funding, entry/exit costs, reserve
returns and births. Shared EMA crossing predicates preserve existing Probe
behavior; an independent comparison checks all 59 derived EMA periods against
the actual candle-history implementation. Reference-price stop/take thresholds
include exact equality at 97%/107%, separate from adverse execution fills.

Version 3 of the isolated command fixture binds the prior and candidate state,
source/action/threshold/cursor evidence, complete evaluation/selection,
optimizer/RNG evidence and ordered events in the same fenced transaction as
the economic rows and immutable response. Empty economic batches still bind
full source/indicator checkpoints. Rejected metadata or late operations roll
back every projection and event. Replaying the same request returns the
original result; changed requests conflict. Interrupted runs retain their last
checkpoint as evidence without permission to resume from its old status.

The reviewed optimizer codec preserves ordered maps, aliases, numeric array
types and complete RNG states without pickle or serialization hooks. CMA
0.13.1 has an uninitialized fitness-history buffer; only initialized slots are
read and the remainder are explicitly marked unwritten. SQL validates evidence
shape and bindings, exact monetary arithmetic and position counts; it does not
independently rerun EMA, fitness or optimizer selection mathematics.

This path remains disconnected from Genesis/application persistence and the
cloud schema. It does not implement the full controller's risk-latch,
early-terminal-member, stop/pause, recovery, diversity or auto-spawn lifecycle.
There is no legacy float-position import, checkpoint decoder, hosted worker,
provider collection or live signing/trading. Parent C2, C3, D/A3 and hosting
remain open. [Rehearsal contract](services/vonneumann/EXACT-ENGINE-REHEARSAL.md)
records the precise admission policy and further research.

**Validation:** all 972 ordinary worker tests pass, including 42 new cases
covering exact preparation, optimizer encoding, transition validation and
indicator equivalence. Discovery reports 978 tests in 74.140 seconds with ten
skips: six opt-in PostgreSQL test cases and four PostgreSQL class-level skips.
The nine new targeted PostgreSQL cases also pass against the frozen fixture.
They exercise every transition from all four real solvers across three traded
replacements, equality and one-quantum threshold neighbors, malformed optimizer,
EMA and completed-evaluation evidence, unchanged source on rejection, original
command resolution, full rollback and preserved interrupted checkpoints.
The final complete PostgreSQL regression suite passes all 68 tests in
197.490 seconds, including the 59 prior contract regressions. Its owned
no-network temporary database container was cleaned up by the harness.
Frontend tests were not rerun for this Python/isolated-SQL slice; exact Vercel
Git builds and read-only production smoke checks remain release gates.

**Capacity and next research:** whole payloads retain the 262,144-byte cap in
addition to 32 retained accounts and 64 positions. Three-window maxima are
161,733 bytes (GA), 175,582 (DE), 209,607 (PSO) and 228,799 (CMA). A denser CMA
trace exceeds the cap and rejects without changing its source; position-count
ceilings do not guarantee that every complete checkpoint fits. No cap increase,
partial replacement or evidence truncation is introduced. A diagnostic that
aggregated full command journals exhausted the disposable database's 512 MiB
allowance; tests now aggregate bounded row digests instead. Research paginated,
byte-bounded journal/outbox reads and retention before cutover. Source numeric
lexemes/manifests, numerical conversion policy, full lifecycle acceptance and
worst-case payload/RSS/transaction/lease measurements remain C2 work.
**Next implementation is C3:** retain a candidate through submission and late
acknowledgment, install only its matching committed result, and deliver stable
event IDs after installation without another optimizer tell/ask.

**Security follow-up:** current official release/advisory metadata still has
Next.js/eslint-config-next 16.3.8 as the latest stable release. One critical and
one high issue remain pending upstream coordination; SEC-05 stays open. No new
package installation or fresh full dependency audit is claimed.

**Verified targets and release plan:** GitHub `TOOTRJ/TheDashboard`
(`1141090963`); Vercel `the-dashboard` (`prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`), team
`team_8iNNxiNjrOseD4gdSCHkQEzF` / `orderoftheredjester`; Supabase `The Dashboard`
(`fxpxsciltakyypunglzr`), organization `cqfnnaunmupdyobkyqfo` / `Valentine Jester`,
ACTIVE_HEALTHY. Canonical origin and both local pins match. The dedicated
Dashboard Vercel session expired during verification; the user renewed only
that profile, and exact target checks then passed again. No shared/default
profile or another project's configuration was changed. PR31 merge
`2f42831c571de32c2636842c24198fde8fbc72b4`, READY production
`dpl_6jUjGMaRFGftYBdqbbLDvFxhAStx`, is the rollback baseline. Verify the exact
source preview and author before merge; verify production's exact merge/alias
and four read-only smoke checks afterward. Record release evidence in the PR.
A reviewed code revert is sufficient; this fixture is outside migrations and
there is no cloud schema/environment/data rollback. The historical migration
edit retains SHA-256
`a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc` and is excluded.
Unrelated local files and the other agent's tools, credentials and processes
are preserved.

## 39. Acknowledged installation and ordered outbox (DB-03A2C3, 2026-10-02)

**Scope:** the bounded v3 rehearsal now has one coordinator that retains the
exact candidate and prepared command before submission, validates the complete
matching acknowledgment and exact reserve, then synchronously installs one
state pointer. Its owned shielded task survives caller cancellation through
late acknowledgment and installation. Original-ID readback or a matching late
repository receipt resolves uncertainty without another command or optimizer
tell/ask. Missing evidence and failed installation block further decisions.

Drain remains permanent through submission, readback, installation and delivery.
Heartbeat cannot renew an unresolved/uninstalled candidate; after installation
it can renew between delivery attempts without reopening economic admission.
Only demonstrably unsubmitted local scheduling/admission failures discard the
attempt. That proof requires an unopened task barrier or unchanged repository
receipt identity/revision/fence/status/version with no pending/busy request.
Cancellation and uncertain transport results never use this cleanup.

SQL materializes immutable candidate events in the same transaction as state,
economics, command and receipt. One separate publisher checkpoint acknowledges
only a contiguous ordered prefix. Page responses are bounded to 100 events and
65,536 complete UTF-8 bytes; neither full state journals nor an unbounded event
aggregate is read. The coordinator independently matches every returned event
to its installed retained candidate before publication. Delivery reads/acks
are lease-free and grant no economic or restart authority.

**Review fixes:** a command UUID is unique only within a run, so event IDs use
`run_id:command_id:event_index` and records carry owner/run routing. Otherwise a
shared deduplicating relay could discard different runs' events as duplicates.
A syntactically valid but wrong exact reserve is now rejected before repository
adoption. Heartbeat after a failed install is explicitly blocked. A successful
callback plus a lost database delivery ack retains an ack-only retry; ambiguous
callback completion permits duplicate delivery of that same stable identity.
Consumers must deduplicate. No exactly-once network or browser-wide delivery is
claimed. Independent implementation and SQL review found no remaining blockers
within this declared scope.

**Validation:** all 1,004 ordinary worker tests pass, including 32 new independent
coordinator cases. Discovery reports 1,010 tests in 92.133 seconds with 12 skips:
six explicitly opt-in PostgreSQL test cases and six PostgreSQL class-level skips.
Actual replacement candidates from all four solvers cross the coordinator while
optimizer evolve/CMA ask/tell are patched to fail if repeated. Other cases cover
late/canceled replies, forced outer-task cancellation, invalid/missing readback,
install failure, typed full-state identity, partial publication and lost acks,
run-ID collisions, eager task factories, scheduling failures, lease/drain races,
and detached callback payloads. Nine new focused real PostgreSQL cases also
pass, including a complete first CMA replacement whose lost reply resolves by
the original ID after lease expiry. The final full PostgreSQL suite passes all
77 tests in 223.945 seconds, including the 68 previous contract cases; its owned
no-network database container was cleaned up. Frontend tests are not rerun for this disconnected Python/SQL
slice; exact Vercel Git builds and four read-only production smokes remain gates.

**Remaining work and research:** this is in-process installation/delivery for a
fresh bounded run. No historical-state decoder, active-controller replacement,
production relay, lifecycle/browser notification coverage or unattended worker
is introduced. The next implementation is C2C full risk/terminal/pause/stop and
evidence-backed recovery transitions, then remaining C2 source/provenance and
capacity acceptance before D/A3 transport, grants, legacy compatibility and
migration. Research relay ownership/durability, receiver deduplication retention,
browser routing/reconnect, journal/outbox archival, body limits before decoding
and production lease timing. The one-transition outbox gate bounds backlog but
can delay protective decisions under a slow relay; measure that effect before
considering bounded decoupling. [C3 contract and primary research sources](services/vonneumann/ACKNOWLEDGED-TRANSITIONS.md).

**Target/release and rollback plan:** freshly verify repository
`TOOTRJ/TheDashboard` / `1141090963`; Vercel `the-dashboard` /
`prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`, team `team_8iNNxiNjrOseD4gdSCHkQEzF` /
`orderoftheredjester`; Supabase `The Dashboard` / `fxpxsciltakyypunglzr`,
organization `cqfnnaunmupdyobkyqfo` / `Valentine Jester`. Canonical origin and
local project pins must match. PR32 merge
`3ce23678c758675a4e9c3435f6f371431541ae5e`, READY production
`dpl_3CeuUP4MHX2F4n7ecSY257wQ7eSL`, is the rollback baseline. Verify source preview
and author before merge, then exact production merge/alias and read-only smokes;
record actual release evidence in the PR. A reviewed code revert is sufficient:
the SQL remains outside the migration path, with no cloud schema/data/env change.
The pre-existing historical migration edit remains excluded with SHA-256
`a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc`. Other local
files, projects, shared credentials/settings/tools and processes are preserved.


## 40. Exact lifecycle extension — implementation and acceptance (2026-10-02)

**Scope:** DB-03A2C2C is a fresh-run v4 extension to the bounded EMA rehearsal.
Version 3 remains unchanged. The pure planner now stages original-capital loss
latches, drawdown terminal cash/results, pause/stop, and explicit trip-bound
recovery followed by a complete unscored fresh-funded restart. Current history
is required for new evaluation windows. The coordinator carries v4 through its
existing original-command acknowledgment, installation and ordered outbox gates.
The active application controller and cloud database are not switched over.

**Findings fixed during independent review:** pause during warmup previously
rejected each not-yet-ready candidate and could never accumulate enough resumed
history; the new path admits history-only candidates. A long pause could also
reuse 61 old candles as readiness; restart and new-window activation now require
current completed history. Risk evidence preserves the first exact crossing,
including before protective closes and after each cost, so later operations
cannot hide it. A simultaneous colony trip and member death is deliberately
unscored under this conservative v4 ordering. Early-dead candidates remain in
the original full evaluation, and already reclaimed cash cannot be retired twice.

**Ordinary acceptance:** all 1,052 ordinary worker tests pass, including 48 new
cases (19 lifecycle, five history/profile-containment, 20 protocol and four
coordinator cases). Final discovery reports 1,058 tests in 123.722 seconds with
15 skips: six explicitly opt-in PostgreSQL cases and nine class-level skips.
The unchanged-version protocol/repository/lineage/coordinator subset also passed
all 110 cases. Independent review verified that non-aborted unchanged strategy
state preserves its exact encoded map order/aliases; primitive mirror expansion
has separate depth/visit/byte limits. The focused PostgreSQL run passed all 17
loaded cases in 204.355 seconds. The final complete PostgreSQL run passed all
95 cases in 413.948 seconds, including 18 new positive, adversarial and delivery
cases. Raw monetary JSON numbers, omitted required deaths, changed frozen scores,
incorrect trip identity, incomplete lineage and expired-window no-ops are rejected.
SQL binds lifecycle economics and cohort mirrors while keeping existing versions
available under their original rules. The fixture remains outside the Supabase
migration path; test containers are isolated from the production database.

**Target/release and rollback plan:** fresh checks passed for
`TOOTRJ/TheDashboard` / `1141090963`; Vercel `the-dashboard` /
`prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`, team `team_8iNNxiNjrOseD4gdSCHkQEzF`;
Supabase `The Dashboard` / `fxpxsciltakyypunglzr`, organization
`cqfnnaunmupdyobkyqfo`. Reverify before push/merge. PR33 merge
`a922dda0649947e6487be0e185b1cc88f6260871`, READY production
`dpl_7hGboRLTiP2DmgLDuWZ17HzJ3TEn`, is the rollback baseline. Verify the exact
source preview and merge production/alias, then the four read-only application
smokes. Record immutable release evidence in the PR. Rollback is a reviewed code
revert; no production data/schema/env change is introduced. Preserve the existing
historical migration edit (SHA-256
`a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc`) and other
local files, projects, credentials, tools and processes.

**Remaining gates and research:** next is C2D exact source/provenance and
operational failure admission, then supported capacity/broader-profile acceptance
and D/A3 transport/grants/legacy cutover. Fixed zero lifespan is not age-based
termination coverage. Research post-acknowledgment freshness, source/currency
semantics, repeated-interruption capacity, relay latency/deduplication, and
journal/outbox retention before expansion. A failed pure protective candidate
leaves its source unchanged; the future runtime must independently halt decision
admission and never reuse an older frame. A delayed recovery receipt establishes
a commit, not current market freshness. See [the lifecycle contract](services/vonneumann/EXACT-LIFECYCLE.md).


## 41. Exact provider evidence — C2D1 (2026-10-02)

**Scope:** both active paper adapters now capture bounded raw JSON before producing
legacy float views. Immutable price/candle records derive values from their owned
response documents; canonical safe requests, body/request digests, parser policy
and receipt clocks retain provenance. Exact candles distinguish base-token and USD
volumes and retain scaling metadata. Unknown/invalid wire forms fail without a
partial cache update. No provider API credentials were printed, no authenticated
market acquisition was made, and no shared tooling/configuration was changed.

**Review findings fixed:** legacy mutable ticks could otherwise contaminate cache
source-age evidence; fresh views now come from immutable captures. Exact overlap
comparison initially remembered only the last small request window, so a later
warmup could miss an older candle revision hidden by float precision. Bounded
4,096-minute exact fingerprints now survive those window changes, with complete
batch atomicity and no indefinite raw-response retention. A same-minute explicit
warmup now refetches when the cached incremental request did not cover its wider
window, instead of returning too little history.

**Research:** current official Jupiter/Birdeye/Solana documents confirm that source
numeric tokens must be preserved before binary64 conversion, token decimals do
not define USD-price precision, and candle time is the open. Jupiter's block-ID
to RPC-slot mapping is not unambiguously specified; the existing local resolver
policy is explicitly labeled. Adjacent slots can share estimated seconds, which
is incompatible with a direct adapter to the synthetic exact planner's strict
increasing timestamps. Full provider binding therefore remains C2D2 rather than
silently changing v3/v4 meaning. [Research](services/vonneumann/EXACT-SOURCE-RESEARCH.md)
and [implemented scope](services/vonneumann/EXACT-PROVIDER-INPUTS.md) retain deeper
publication/revision, currencies/scaling, memory and latency questions.

**Acceptance:** all 1,125 ordinary worker tests pass, including 73 new cases
(26 document/parser, 25 exact records and 22 actual-adapter integration). Final
full discovery reports 1,131 tests in 169.121 seconds, with 15 skips: six explicitly
opt-in PostgreSQL cases plus nine class-level skips. The first full run exposed
an inherited sticky Decimal flag in a new test; clearing the local context's flags
before its assertion fixed test isolation, and the final full rerun passed.
Existing 80 provider/freshness tests also pass. There is no SQL, command version
or migration change in this increment; the prior 95-case isolated database
acceptance is not claimed as a new run here.

**Target/release and rollback plan:** verified GitHub `TOOTRJ/TheDashboard` /
`1141090963`; Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`,
team `team_8iNNxiNjrOseD4gdSCHkQEzF`; Supabase `The Dashboard` /
`fxpxsciltakyypunglzr`, organization `cqfnnaunmupdyobkyqfo`. Reverify before remote
writes. PR34 merge `ce8433c7f8899d13b8c1f252d40df72d6c821ec7`, READY production
`dpl_9yaANPAh5sKhRKLQ9yDwTMGPqhUm`, is the rollback baseline. Verify the source
preview/author, exact production merge and alias, then four read-only application
smokes. Record immutable release evidence in the PR. Rollback is a reviewed code
revert; there is no production database or environment change to reverse.
Preserve the existing migration edit with SHA-256
`a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc`, `.claude/`,
other local files, shared credentials/tools/processes and all other projects.

**Next:** C2D2 provider command binding and the operational freshness/failure owner,
then broader capacity acceptance and D/A3 transport/legacy/grant cutover. The
active controller still uses float compatibility views. The worker remains
unhosted, and no signing, funding, swap or live trading action is enabled.

## 42. Operational admission owner — C2D2A (2026-10-02)

**Scope:** a fresh v4 `RehearsalAdmissionOwner` owns preparation, submission,
acknowledgment installation, readback and ordered event delivery. Owner-issued
immutable synthetic quotes preserve their original receipt clocks; ordinary
decisions and recovery require the same accepted protective ticket. Receipt
expiry is an explicit local processing-wait budget, independent of simulated
event time. The source remains `synthetic-exact-fixture-v1`; there is no new
provider/command version, SQL/schema change or active-controller cutover.

**Failure and commit handling:** admission checks surround planning and run inside
the repository-owned task just before transport dispatch, after request
materialization. Lease and permanent closure are rechecked at that boundary.
Only a proven pre-dispatch failure clears an unsent attempt; all post-dispatch
uncertainty retains the original command. Guards run after awaited acknowledgment,
readback, heartbeat and outbox boundaries. Expired committed work still installs
and publishes while future economics remain closed. Planning/ID/body-capacity
failures cannot reuse an old unconsumed frame. Explicit canonical command IDs are
required; a bounded 4,096-ID set includes creation and rejects reuse without
eviction or random fallback. Caller cancellation preserves ownership.

**Review findings fixed:** async scheduling gaps could consume a quote or lease
after an outer check; dispatch now has its own final check. Monotonic rollback
could invalidate a repository lease without setting the owner's permanent latch;
owner checks now run first and latch failures. A task factory raising
`CancelledError` could bypass an `Exception` scheduling handler; the owned
scheduling boundaries handle it explicitly. `command_id=None` could otherwise
reach the protocol's UUID fallback; the owner rejects it before planning.

**Acceptance:** all 1,183 ordinary worker tests pass, including 58 new cases
(30 owner and 28 dispatch/coordinator). Full discovery completed 1,189 tests in
170.555 seconds, with 15 skips: six explicit opt-in PostgreSQL cases and nine
class-level database skips. The separate complete PostgreSQL suite passed all
95 tests in 529.126 seconds; the harness removed all of its labeled isolated
containers. Later scheduling/clock-exception refinements also passed focused
regressions and the final ordinary suite; no SQL changed.
Independent tests cover real exact lifecycle warmup/entries/risk/recovery,
expired recovery replies, unsent scheduling failures, command identity limits,
lost/missing/corrupt readback, installation retries, cancellation, and committed
delivery after closure. See [the contract](services/vonneumann/OPERATIONAL-ADMISSION.md).

**Target/release and rollback plan:** read-only checks matched GitHub
`TOOTRJ/TheDashboard` / `1141090963`; Vercel `the-dashboard` /
`prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`, team `team_8iNNxiNjrOseD4gdSCHkQEzF`;
Supabase `The Dashboard` / `fxpxsciltakyypunglzr`, organization
`cqfnnaunmupdyobkyqfo`. Reverify before push/merge. PR35 merge
`0595a311d14fd8c5e28d6c23d840dc4f3f1733cd`, READY production
`dpl_FZGDLGB2xsDU9JeHrJyD9bDWk71n`, is the rollback baseline. Verify exact source
preview/author, production merge/project/team/alias and the four read-only app
smokes. Record actual release evidence in the PR. Rollback is a reviewed code
revert; no production data, schema or environment change is introduced. Preserve
the historical migration edit with SHA-256
`a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc` and all other
local files, projects, shared credentials, tools and processes.

**Next and deeper research:** C2D2 still needs a new provider-source/command
contract and SQL checks separating source ordering, source time, local receipt,
decision time, availability and restart watermarks. The primary Jupiter/Birdeye/
Solana documents were rechecked; Birdeye WebSocket closes can change within an
interval and do not establish final publication. Research same-slot/equal-second
updates, block/slot/fork mappings, outlier/revision semantics, USD/scaling,
restart clocks, source/lease/relay latency and worst-case memory before adoption.
Then prove active-controller ownership and capacity, followed by D/A3 production
transport, legacy/grants and migration. The worker remains unhosted.

## 43. Provider-bound command and historical startup — C2D2B (2026-10-02)

**Scope:** fresh version 5 binds exact Jupiter price/Birdeye candle captures to
run policy, owned state, commands and the isolated SQL contract. Wrapped SOL,
nine token decimals, unscaled USD price candles and the existing exact price grid
are pinned. The model uses `SOL/USD` reference marks, with an explicit typed
optimizer configuration; the active controller's tradeable asset registry is
unchanged. Existing synthetic versions retain their original meaning.

**Time and history:** increasing block references are separate from nondecreasing
estimated source seconds, original receipt clocks and actual decision seconds.
Equal estimated seconds are valid; same-source/same-second deferral cannot renew
anchors or bypass freshness. Integer microsecond conversion floors receipts and
ceils current samples using their original exact ratios. Carried source-age floors
survive unequal clock progress. Every new provider command has receipt/source
freshness checked in the owner and at SQL server boundaries. The server rejects
future decision envelopes; strict admission requires clock/latency measurements
before deployment. Original-ID replay retains the prior committed receipt.

Startup seeds 61 completed 15-minute closes from 915 exact historical minute
records **at actual current receipt time**, with no retrospective decisions,
fills or scores. Current next-bar admission rejects gaps/revisions; nonmarket
controls retain source state, while halted protection/eligible exits need no new
candle. The owner retains source receipts through acknowledgment and delivery;
expiry closes future economics without discarding acknowledged state/events.

**Trust and review:** manifests record safe request/parser/response identities;
SQL checks their shape and the worker-declared consumed rows, not provider
truth/raw-body derivation. Python recomputes seeded EMA values; SQL validates
seed shape/source binding and existing exact economics, not binary64 indicator
or optimizer mathematics. Prequote seed validation uses only explicit local
empty-EMA projections. Review caught stale deferral, weakened source-age floors,
omitted-history admission, seeded prequote compatibility, PSO/CMA typed optimizer
state, source/prepare clock separation and caller-owned record-list mutation.

**Acceptance:** all 1,229 ordinary worker tests pass, including 46 new provider,
owner and source-boundary cases. Full discovery completed 1,235 tests in 147.112
seconds with 16 skips: six explicit opt-in database tests and ten class-level
skips. Final focused source-clock refinements also passed. The complete isolated
PostgreSQL suite passed all 110 tests in 397.093 seconds, including 15 new provider
cases; focused provider acceptance also passed all 15 in 21.166 seconds. The
harness removed all of its labeled local containers. Real tests cover fresh
admission, server expiry before/after effects, full rollback, old-ID replay,
request/time/source tampering, private helper boundaries and current-clock
startup/protection/decision for all four solvers. Simulated-hour provider
replacements remain offline tests; the SQL has no test-only clock override.
The independent one-window traces measured 68 complete v5 payloads; the largest
was a 188,148-byte CMA replacement, below the unchanged 262,144-byte cap. This is
not worst-case capacity or a production performance measurement.
The guarded SQL remains outside
`supabase/migrations`; tests use offline mocked inputs and uniquely owned local
no-network PostgreSQL containers. No production database data/schema, environment,
worker hosting, signing or live trading change is part of this increment.

**Targets/release and rollback:** initial read-only verification matched GitHub
`TOOTRJ/TheDashboard` / `1141090963`; Vercel `the-dashboard` /
`prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`, team `team_8iNNxiNjrOseD4gdSCHkQEzF`;
Supabase `The Dashboard` / `fxpxsciltakyypunglzr`, organization
`cqfnnaunmupdyobkyqfo`. Reverify before remote writes. PR36 merge
`b1abcfdd1c4a166bbe330210cfaf928d5de2d4ad`, READY production
`dpl_93FPzLTGUDbd2TbseQAX9CSGC1CP`, is the rollback baseline. Release requires
verified source preview/author, exact production merge/project/team/alias and
four read-only application smokes; record immutable results in the PR. Rollback
is a reviewed code revert; no database or environment reversal is required.
Preserve the historical migration edit SHA-256
`a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc`, `.claude/`,
other local files and all shared credentials/tools/processes and other projects.

**Next and deeper research:** prove active-controller ownership and supported
whole-command capacity/latency, then D/A3 production transport, legacy/grants,
checkpoint recovery and reviewed migration cutover. Hosting remains gated.
Research block/slot/fork mapping and same-block changes, provider publication/
revision/outlier semantics, receipt/lease/relay and protective latency, USD/USDC
and scaled-token expansion, restart clock/history reconciliation, data rights,
frozen reproducible datasets and capture/journal/outbox memory/retention.
See [the provider contract](services/vonneumann/PROVIDER-COMMAND-CONTRACT.md).

## 44. Provider acquisition and later-generation capacity — C2D2C (2026-10-05)

**Scope and findings:** the executable v5 owner still has no active service
controller. Review identified two immediate acquisition blockers: the general
Birdeye incremental cache contains only roughly three minutes, and continuously
replacing a fractional Jupiter receipt can perpetually defer its admission.
The new opt-in history API acquires one current 915-minute seed or a 30-minute
full prior/new-bar window, with raw wrapped-SOL/USD records, original document
identity and strict completion/coverage/freshness checks. It leaves the legacy
feed caches and installed owner cursor untouched. The owner independently
compares overlap. No new eligible bar performs no HTTP; a multi-bar gap fails
visibly. A retained-price helper uses the actual owner clock on retries and
preserves cancelled callers' original task/result. It has no economics,
publication, service routing, migration or wallet-execution authority.

Independent review found and fixed cancellation before the owned coroutine's
first instruction and late successes after a dependency suppresses cancellation.
Both acquisition APIs now explicitly check their event-loop deadlines after
awaits and synchronous parsing. A late result rejects even when receipt clocks
look fresh; these checks cannot preempt CPU work. The new price helper's lock
covers acquisition only: a future exact controller must own the entire tick
and every control across commit/reconciliation/publication.

**Capacity is still a blocker:** three sparse replacements fit all four solvers,
with maximum GA/DE/PSO/CMA payloads 162,965/172,688/218,286/218,343 bytes. Denser
alternating-candle retention gives successful third GA/DE replacements of
234,635/244,358 bytes (48 positions). PSO's third model payload already reaches
262,546 bytes; CMA's second full v5 payload reaches 262,797 bytes (its model is
248,760 bytes). Both exceed the unchanged 262,144-byte cap below the separate
position-count bound, and reject without advancing sealed optimizer/cohort/RNG
state. v5 now emits an explicit payload-capacity error. No thresholds are raised,
evidence truncated or complete commands split. The 4,096-ID owner permits only
2,047 complete protect/decision pairs after creation/bootstrap; a first one-hour
1 Hz window needs 7,204 commands. Sparse time jumps establish retention mechanics,
not sustainable cadence or production latency. Instrumented eight-trace capacity
replay took about 29.35 seconds locally, excluding providers/database/publication.

**Validation:** 67 new tests cover acquisition, full-window source consumption
and actual later-generation v5 command encoding. They include real-owner
bootstrap/next-bar installation and stable outbox IDs, original fractional
receipt retention, unchanged-anchor expiry, lost waiter/results, single-owner
admission, missing/invalid/scaled/gapped/revised data, clock/window changes,
cleanup and cancellation/deadline overruns. Independent six-case review passed;
83 existing focused feed/provider regressions also passed. Final full discovery
ran **1,302 tests in 180.422 seconds**, passing with 16 expected opt-in/database
skips; the 67-case final focused run passed in 34.841 seconds. The dedicated
GitHub helper's 16 offline tests also passed. Release results are recorded with
the PR when complete. SQL is
unchanged; the prior 110 isolated PostgreSQL cases are historical acceptance,
not rerun for this acquisition-only increment. All tests use fake provider I/O
and isolated locked Python dependencies, with dotenv disabled and network denial.

**Targets and release gate:** initial provider metadata matched GitHub
`TOOTRJ/TheDashboard` / `1141090963` and dedicated `biggrizzly11` / `16749816`;
Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`, team
`team_8iNNxiNjrOseD4gdSCHkQEzF`, Git repository ID `1141090963`;
Supabase `The Dashboard` / `fxpxsciltakyypunglzr`, organization
`cqfnnaunmupdyobkyqfo`. Local pins matched. Later release verification found
missing authentication in the exact dedicated Vercel profile. Its isolated
login to `/Users/redjester/.config/vercel-dashboard-codex` was renewed before
release, and all three exact target identities were freshly reverified.
Preview/production release verification remains required. Never fall back to Claude/shared
credentials. Fresh Dashboard GitHub verification and remote main readback passed.
PR37 merge `0983468d09ee7a295d7601c2872240ad0204775e`, READY production
`dpl_GPuBG8AKAg8zaPqqRgwwoLKmFsYm`, is the rollback baseline. Reverify targets,
source preview/author, production merge/project/team/alias and four read-only
application smokes; retain immutable results in the PR. Rollback is a reviewed
code revert; this increment requires no database/environment reversal.

The pre-existing migration edit remains byte-identical at SHA-256
`a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc`.
`.claude/`, other local files, shared credentials/tools/processes and all other
projects are preserved. The worker remains unhosted. No cloud database,
application environment, funding, signing or live trading changes are included.

**Next:** C2D2D first proves a supported representation/profile and reserved
command/control budget, then an executable exact controller; D/A3 still gates
production transport, legacy/grants/archive compatibility and migration. Keep
parent C2D2/C2/D/A3 and hosting open. Deep research covers bounded checkpoint /
journal / historical-position retention and replay proofs, real cumulative
provider/lease/relay latency, slower-cadence protective exposure, shared provider
quotas, source forks/revisions/outliers and restart/history reconciliation.
See [the contract](services/vonneumann/PROVIDER-COMMAND-CONTRACT.md) and
[current primary-source recheck](services/vonneumann/EXACT-SOURCE-RESEARCH.md).

## 45. Bounded provider pilot and terminal reserve — C2D2D1 (2026-10-05)

**Implemented scope:** a separate opt-in v5 owner admits only one evaluation
window/first replacement, with 3,601 accepted quotes, 3,600 quote seconds, 4,000
total command IDs including creation/bootstrap/stop, no restart/resume/recovery,
and bounded allocation inputs. It keeps the two EMA genes and all exact economic,
source, optimizer, RNG and event evidence. The active service selection and
legacy controller/writers remain unchanged.

Each prospective nonterminal state must produce a pure complete v5 stop using
maximal clocks and empty allocations. The reserve covers both PostgreSQL-spacing
UTF-8 payload and compact ASCII candidate bytes, plus a derived nine-byte clock
width margin. A distinct stop ID and last command slot cannot be spent by other
work. Actual stop is prepared with current clocks, uses its original reserved
ID through uncertainty/cancellation, and retains holdings/cash/reserve. The
reservation proves bytes and identity capacity, not a lease or network delivery.

The pilot's policy-refusal latch is separate from the existing hard-failure
latch. Normal capacity/duration/completion refusal can retain terminal admission
after settlement. Clock/source/ownership failures still close it. Review fixed
unretained quote windows incorrectly expiring stop after a rejected decision,
new-bar scheduling before the five-second completion margin, and the need to
reserve both JSON encodings for Unicode names. Retained command/publication
evidence is preserved. Typed capacity errors retain old v3/v4/v5 rejection
semantics; neither SQL meanings nor any cap increased.

**Acceptance:** all 44 new focused cases pass with denied network access,
literal provider fixtures and real solvers/candidate/command validation. Coverage
includes dense all-solver first replacement, pure repeated solver/RNG/state
preparation, legal 128-byte Unicode names, clock-width and inclusive-cap bounds,
creation/quote/command/duration accounting, reserved ID exclusion, no-op decision
suppression, pause/stop retained holdings, delayed stops after soft refusal,
hard failures, caller/task/early-task cancellation, lost acknowledgment,
reconciliation and publication. The full worker suite ran **1,346 tests in
226.816 seconds**, passing with 16 expected opt-in/database skips. The 35-case
policy/existing capacity/provider-owner regression run passed; all 16 dedicated
GitHub helper tests passed and `git diff --check` passed. Exact release results
are recorded in the PR. SQL is unchanged; the prior
110 isolated PostgreSQL tests remain historical acceptance, not a new rerun.

The reusable offline measurement CLI exercises the actual pilot and fake
ledger/outbox through 22 economic commands per solver, one suppressed decision,
16 retained accounts/positions and complete stable-event acknowledgment. Largest
actual SQL-spacing payloads GA/DE/PSO/CMA are 162,750/165,918/201,885/207,017 bytes;
maximum reserved stop bounds are 162,770/165,938/182,904/198,136 bytes. Longest
owned preparation/validation/fake-RPC operations measured approximately
0.123/0.121/0.153/0.140 seconds; total traces approximately
2.04/2.04/2.79/2.50 seconds. Sparse clock jumps and fake lease heartbeats are
explicit. These numbers exclude real provider/DB/socket/durable-relay latency;
they do not select cadence or prove the cumulative five-second budget.

**Targets and release:** fresh verification matched dedicated GitHub
`biggrizzly11` / `16749816`, `TOOTRJ/TheDashboard` / `1141090963`; Vercel
`the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`, team
`team_8iNNxiNjrOseD4gdSCHkQEzF`; Supabase `The Dashboard` /
`fxpxsciltakyypunglzr`, organization `cqfnnaunmupdyobkyqfo`. Both local pins
match. Existing PR38 merge `bdd22d3d46d04203541b4390761b6f813ec4f7e7` and READY
production `dpl_71MaCDF8n6aeUDTZFJZushBJNLCj` are the rollback baseline. Verify
the exact preview source/author and production merge/project/team/alias, then
run the four read-only application smokes; record immutable results in the PR.
Rollback is a reviewed code revert and needs no database/environment reversal.

The pre-existing migration is byte-identical at SHA-256
`a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc`.
Untracked `.claude/`, service `.next/`, Supabase temporary files, shared tools,
credentials/processes and all other projects are preserved. No database,
environment, funding, signing or trading change is included. The worker remains
unhosted and inactive.

**Next priority:** C2D2D2 executable whole-tick/control ownership and cumulative
latency acceptance, then D/A3 production transport and complete legacy/grant/
archive/migration cutover, then hosting readiness. C2D2D3 separately researches
a v6 prior-command reference to remove duplicated checkpoints before multi-window
expansion. Preliminary PSO/CMA sizing suggests 150,496/143,497-byte compact
commands, but no v6 candidate is admitted or implemented. Deep substantial
research must cover bounded logical expansion, original-request replay,
prior-journal retention/availability, corruption/revision checks, source/server
freshness, control reserve, clock/history restart, shared quotas and cumulative
protective latency. Parent C2D2/C2/D/A3 and hosting remain open. See
[the pilot contract](services/vonneumann/PROVIDER-PILOT-CONTRACT.md).

## 46. Executable provider controller and bounded runner — C2D2D2 (2026-10-05)

**Implemented local scope:** `ProviderPilotController` exclusively owns fresh
bootstrap, complete ticks, pause, reserved stop and settlement through the real
provider adapters and strict pilot owner. Retained phases bind the original
ticket/history/allocation, successor revision and continuation before submission.
Readback installs/publishes that exact command and renews its lease before any
remaining new economics. No-op decisions avoid history/allocation/dispatch.
Publication resumes only the original stable event prefix. Caller cancellation
retains the whole operation/result; explicit task interruption also retains and
consumes any shielded provider read before reporting idle.

The separate finite runner requires explicit interval and attempt bounds,
rejects intervals at/beyond the controller's lease, and schedules the next
attempt after completion plus that interval. It has no catch-up queue or hidden
heartbeat worker. Caller interruption drains future ticks; explicit stop wakes
waiting work and uses reserved terminal capacity after original work settles.
Uncertainty/publication failure requires explicit settlement, without automatic
retry spinning. Retained result identity prevents an older completed tick from
being counted as a rejected new operation. Pacing-clock failure drains scheduling
but does not prevent original command/event settlement. Natural finite completion
does not automatically spend a stop command.

Review also repaired acquisition's rejection of the exact pilot owner and its
conversion of ordinary pilot refusal into a hard failure; unretained decision
windows incorrectly expiring delayed stop after drain; repeated uncertain
pause/stop trying a second control after successful readback; and foreign-loop
or interrupted-task paths dropping original ownership. Strict candle completion
boundary crossing can still close the pilot safely; supported boundary deferral
remains explicit follow-up research. Pause/stop preserve holdings/cash/reserve.

**Offline acceptance:** all 58 new focused cases pass (35 controller and 23
runner; 17.526 seconds). Complete worker discovery ran **1,404 tests in 232.926
seconds**, passing with 17 expected opt-in/database skips. All 18 dedicated
Dashboard GitHub helper tests and `git diff --check` pass. The helper now admits
repository-pinned `pr ready` with no extra flags; new boundary tests reject
foreign selectors, account/repository mismatches and unsupported options.
Literal fixtures
exercise actual provider parsers, strict owner/solver/command validation, open
positions, deadline/clock failures, cancellation and uncertainty. The full suite
ran with dotenv disabled and bytecode writes disabled in the isolated worker
environment; no application/provider credentials were used.

**Completed local database acceptance:** after the user started the existing
Colima daemon, the six new real PostgreSQL controller/runner cases passed in
13.952 seconds and full SQL discovery passed **116 tests in 507.692 seconds**.
No application/fixture/SQL-contract corrections were needed. Actual process and
server clocks, literal Jupiter/Birdeye/Solana documents and the uniquely owned
no-network harness verify the finite runner, cancellation/drain, lost replies,
original-ID readback, lease renewal, reserved stop and stable publication. The
cached ARM64 PostgreSQL 17.6 image is
`sha256:965e2dfb5a23a0d6541b6106541e777b303656ebabd4e878746b189d550c0a66`;
Docker server is 29.5.2. Only the task's uniquely owned containers were removed.
All nine original unrelated container identities remained running; shared
daemon/context/settings were preserved. Ordinary opt-in skips remain distinct
from actual SQL acceptance. D2 is complete as bounded local executable acceptance;
its parents and production gates remain open.

**Current-clock cumulative measurement:** the CLI passed with three accepted
quotes, final revision 7/stopped, exact SQL projection and 11 unique fully
acknowledged events. Five observed accepted-operation / first-request-through-
completion times in milliseconds are: bootstrap **645.382 / 645.550**, first
quote/protection/decision **344.824 / 442.211**, second quote **190.775 / 800.938**,
third quote **212.108 / 1,010.231**, and reserved stop **288.205 / 288.570**. The
requests include 1/7/9 actual receipt deferrals. Cumulative owner submission
peaked at 311.138 ms for the two-command first tick; publication measured 356.813
ms for nine bootstrap acknowledgments and 91.312 ms for two stop acknowledgments.
One creation, six economic commits, 22 heartbeats, three outbox reads and 11
delivery acknowledgments were counted. The request total and all-attempt phases
include the original acquisition and real waits, rather than synthetic clock
jumps. This flat-GA/local-sink sample does not measure dense replacement bursts,
provider publication/network, remote PostgREST or browser/durable relay tails,
and does not establish percentiles, worst-case bounds or production cadence.

Reports include elapsed operation and cumulative acquisition, lease, submission,
readback, cleanup and publication phases. Submission includes preparation,
complete stop witness, validation and transport acknowledgment; publication
includes all bounded pages and acknowledgment. The completed real-clock CLI
includes deferred attempts and actual waiting. Fake/controller timing and even
local SQL timing do not establish real provider/remote-database/relay tails,
organization quota feasibility or a sustainable production cadence.

**Exact targets:** fresh identity verification matched dedicated GitHub
`biggrizzly11` / `16749816`, `TOOTRJ/TheDashboard` / `1141090963`; Vercel
`the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`, team
`team_8iNNxiNjrOseD4gdSCHkQEzF`; Supabase `The Dashboard` /
`fxpxsciltakyypunglzr`, organization `cqfnnaunmupdyobkyqfo`. Both local pins
match. PR39 merge `5eb46ea0658e5ef8e7243d75223b217602795119` / READY production
`dpl_FjGjYCXg3AhDw1qkiDcGn3FWtahP` is the verified release baseline. Release
verification is tracked in [PR40](https://github.com/TOOTRJ/TheDashboard/pull/40);
final merge/deployment/alias/read-only smoke evidence will be recorded there
after release. Rollback is a code revert; SQL, caps, schema,
remote environments and service selection are unchanged.

The pre-existing migration remains at SHA-256
`a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc`.
Untracked `.claude/`, service `.next/`, Supabase temporary files and other agent
credentials/tools/processes are preserved. No provider credential was sent,
database migration applied, hosted worker started, wallet signed or trade placed.
See [the controller contract](services/vonneumann/PROVIDER-CONTROLLER-CONTRACT.md)
for the ordered path, measured-evidence limits and remaining deep research.

## 47. Verified production VN inventory and forward cutover — DB-03A2D1 (2026-10-05)

Fresh provider metadata and local pins matched only GitHub
`TOOTRJ/TheDashboard` / `1141090963`, dedicated user `biggrizzly11` / `16749816`;
Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`, team
`team_8iNNxiNjrOseD4gdSCHkQEzF`; Supabase `The Dashboard` /
`fxpxsciltakyypunglzr`, organization `cqfnnaunmupdyobkyqfo`. The cached
database connection username also matches. The unrelated connector, other
project contents, shared credentials and tool/process configuration were not used.

The reviewed [inventory SQL](supabase/audits/vonneumann-cutover-inventory.sql)
executed through Supabase CLI 2.84.2's linked Management API query path. Its
returned context proves PostgreSQL 17.6, repeatable-read isolation, transaction
read-only `on`, lock timeout `1s` and statement timeout `15s`, ending in rollback.
Draft SQL needed the correct existing `metrics` column name before successful
acceptance; failed read-only queries made no mutations. The
[dated JSON snapshot](supabase/audits/2026-10-05-vonneumann-inventory.json)
contains aggregate counts and exact catalog/ACL metadata, with no application
IDs/bodies, credentials, function bodies or unrestricted service configuration.

**Measured data:** 8 colonies (all saved stopped), 497 probes across 24 runs,
807 trades across 15 runs, 9,837 snapshots across 10 runs, zero generation stats.
The populated tables each have one owner. No NULL child run IDs, missing probe
references or observed owner/bound-run disagreements were found. However,
160 probes, 126 trades and 1,098 snapshots lack a corresponding colony row.
The probes represent **16 older runs omitted by current history readback**
because its fallback runs only when colony history is empty. All 497 probe and
9,837 snapshot `metrics` values and all 807 trade `execution` values are SQL
NULL. All new ancestry arrays are empty; 257 scalar parent references remain.
Seventeen trade rows are open. Saved stopped status and these old rows do not
establish monitored exposure, exact balances, cost policy or safe restoration.
No historical data was filled, deleted, adopted or reclassified.

**Measured security/schema:** five `postgres`-owned RLS-enabled tables, no FORCE
RLS; 18 permissive PUBLIC-scoped owner policies, 93 columns, 19 validated
constraints and 25 valid/ready indexes. Nullable run IDs lack colony FKs;
trade/snapshot/parent links are scalar rather than composite owner/run checks.
All eight table privileges, including TRUNCATE/TRIGGER/REFERENCES/MAINTAIN,
are effective for anon/authenticated/service_role; only service_role has
BYPASSRLS. Authenticator has no direct table privileges, but can SET ROLE to
the three API roles without inheriting their grants. The role scan is complete
at its bound and explicit column ACLs are absent. These are privilege/policy
metadata, not actor-specific RLS tests or proof of an exposed truncate RPC.
The related public defaults are broad; do not alter shared postgres defaults
to repair VN. The plan scopes future denial to exact VN objects and installs
new helpers under a separately reviewed dedicated owner.

Both non-internal update triggers are enabled; the colony trigger is already
bound to `extensions.moddatetime`. No durability schema, VN realtime table,
related sequence, immediate dependent view, unexpected VN relation or external
incoming FK was found. All fourteen migration versions match the tracked
filenames. Function discovery covers VN name/source matches, direct dependencies
and bound triggers, but cannot prove arbitrary dynamic SQL/client absence.
Hosted PostgREST version/exposure/transaction-end/JWT configuration and actual
HTTP actor/commit behavior remain unverified; selected database-role settings
are not complete service configuration. The audit output excludes JWT secrets.

The [concrete cutover plan](services/vonneumann/PRODUCTION-CUTOVER-PLAN.md)
maps every active legacy writer, five read projections, archive and relay path,
private/effective grants and rollback order. It identifies two specific projection
traps: retirement sweeps cash to reserve, so post-retirement zero cash is not
terminal capital; newest member/evaluation checkpoints cannot reconstruct full
history. Required projections must commit with commands or have explicitly
accepted durable replay/lag semantics. Current EventPersister and socket broadcast
are not production replacements for atomic projection or durable relay acceptance.

**Next order:** independent merged/paginated legacy history repair, inert pinned
HTTP transport plus actual isolated PostgREST commit/schema/JWT faults, full
versioned projections/archive/relay and forward migration/grant cutover, then
production-source/lease/load and recovery/hosting acceptance. D1 is complete
as this bounded read-only inventory/plan; D/A3, production timing, compact
checkpoint and hosting parents remain open. The TODO now names D1A/D2/D3 and
deep research on custom worker credentials, server transaction configuration,
legacy classification, relay/replay/retention, source quotas and lease headroom.

This release changes only audit/documentation files. SQL is outside migrations;
no application, schema, grant, environment, provider acquisition, hosted worker,
wallet or trade changes are included. PR40 merge
`22af3190c0171671747d69e971807144a2fa3322` / READY production
`dpl_6rxutLU4iyGA3328ZhP7NkePYU4y` remains the verified pre-release baseline.
The inventory PR records its exact source/preview/merge/production/read-only
smoke verification after release. Rollback is a code/document revert. The
pre-existing historical migration still has SHA-256
`a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc`;
unrelated edits/untracked artifacts and shared agent resources are preserved.


## 48. Complete owner-visible legacy history repair — DB-03A2D1A

Prepared 2026-10-05 against PR41 merge `299998ccb9727a23896029a6138b1b526617e142`.
Before implementation, fresh authenticated identity metadata and local pins matched
GitHub `TOOTRJ/TheDashboard` / `1141090963` / verified `biggrizzly11` (`16749816`),
Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` /
`team_8iNNxiNjrOseD4gdSCHkQEzF`, and Supabase `The Dashboard` /
`fxpxsciltakyypunglzr` / `cqfnnaunmupdyobkyqfo`. The dedicated profiles/helper
were used; the mismatched Supabase connector remains unused.

The reader previously returned only colony-derived runs whenever any colonies
existed, omitting the 16 probe-only groups measured in section 47. It now scans
both owner-filtered sources and merges exact run identities after both reads are
complete. Each request includes `user_id = captured authenticated owner`; every
returned row must match that owner. RLS remains in place. Stable exact counts,
strict ascending row IDs, no overlap/duplicates, bounded pages and valid summary
fields are required. Short pages advance by actual length until the exact count;
missing counts, count drift, gaps, malformed values, later errors and exhausted
budgets reject the whole result. No partial summary or empty success hides failure.

Limits are 200 requested rows/page, 50,000 rows/table, 500 pages/table and one
8-second scan deadline. They are local reader budgets, not remote configuration
or a hosted latency/capacity guarantee. Probe requests select only identity,
owner, run, mode, fitness and creation time; saved colony configuration is parsed
through the existing public diagnostic/policy allowlists. Private errors and raw
configuration do not enter returned history or UI messages.

Colony-backed metadata retains known lifecycle/policies. Probe-only metadata has
explicit provenance, unknown colony status/strategy/policies, no inferred end,
and earliest recorded probe creation time labelled **First probe record** rather
than a claimed colony launch. Negative scores remain negative; conflicting legacy
modes stay unknown. The selector is available even for a single recorded run,
and its total counts distinct run IDs across worker and saved lists.

Each page refresh owns an abort controller shared by history and live-list reads.
Superseding refreshes, token replacement, account unmount/logout and disposal
abort retired requests; existing session/list/selection tickets additionally
prevent late publication even if a transport ignores cancellation. Independent
history/worker failures retain their last successful results and remain visible.

**Verification:** 135/135 offline frontend tests pass under bundled Node 24.19.0
(production major remains 24.x). Meaningful cases cover the synthetic measured
shape (8 colonies, 497 probes, 24 total runs, 16 probe-only groups), negative best
fitness on the final page, earliest dates, stable display ties, >1,000 rows,
smaller server row caps, exact page boundaries, count/ID/owner validation, late
failures, finite budgets, abort and retired account/token/run results. Tests use
both query doubles and the actual installed Supabase SDK against fake HTTP
responses to verify owner/count/order/range serialization, Content-Range parsing
and in-flight cancellation. TypeScript passes; lint has zero errors and 33
pre-existing warnings. A default-Turbopack production build passes in a temporary
allowlisted source/dependency copy with fake credentials/`.invalid` endpoints,
no environment files and telemetry disabled; the real checkout's build output
is preserved. No dependency, schema, provider or trading change is required.

[Supabase range](https://supabase.com/docs/reference/javascript/using-modifiers-range),
[exact count](https://supabase.com/docs/reference/javascript/select) and
[abort](https://supabase.com/docs/reference/javascript/using-modifiers-abortsignal)
contracts were checked against current official documentation and the installed
SDK. Cleanup and stale-publication behavior follows
[React effect lifecycle guidance](https://react.dev/reference/react/useEffect).
**Limit:** separate HTTP pages and the two source scans are not a repeatable-read
snapshot. Validation detects count/order/duplicate drift but cannot prove the
absence of every same-count concurrent metadata/fitness edit. D3 versioned server
projections and actual two-owner/anonymous RLS tests remain required. Other probe,
trade, sample and generation detail readers are not fixed by this history repair.

Release gates are fresh exact-target verification, reviewed PR diff, exact-source
READY preview, merge of that reviewed head, exact-merge READY production and four
read-only application smokes. Final immutable identifiers/results belong in the
PR body after release. Rollback is a reviewed code revert to the compatible PR41
baseline; no data/schema rollback is needed. The preserved historical migration
SHA-256 remains `a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc`.
No production history rows, schemas, grants, environment files, shared credentials,
other projects, worker processes, funded wallets or transactions were changed.
D2 inert HTTP transport is next; D3/A3, source/lease/load and recovery/hosting
acceptance remain open.


## 49. Inert command HTTP transport and MVP roadmap — 2026-10-05

**Scope:** DB-03A2D2. `DashboardCommandHTTPTransport` is not imported by application startup or selected for production persistence. It owns a TLS-verified HTTPX client/transport with the exact `fxpxsciltakyypunglzr.supabase.co` origin, `vn_durability` schema, seven immutable RPC signatures and explicit private modern key/owner injection. There are no default credentials, automatic retries/redirects/environment proxy/CA fallbacks, or public endpoint/client overrides. Finite whole-operation/phase/pool/cleanup bounds, bounded exact JSON and retained one-time closure preserve original-command reconciliation. HTTPX 0.28.1 is now a direct runtime input; lock versions and hashes are unchanged, and isolated `pip check` passes. [Complete contract](services/vonneumann/COMMAND-HTTP-CONTRACT.md).

**Fresh exact-target verification:** authenticated metadata and local pins match GitHub `TOOTRJ/TheDashboard` / 1141090963 with dedicated user `biggrizzly11` / 16749816; Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` / team `team_8iNNxiNjrOseD4gdSCHkQEzF`; Supabase `The Dashboard` / `fxpxsciltakyypunglzr` / organization `cqfnnaunmupdyobkyqfo`. Two secret-safe read-only schema GETs report hosted PostgREST **14.5**, HTTPS schemes and **406/PGRST106** for `vn_durability`. No hosted RPC commands, migrations, auth/data records or provider trades were submitted. These reads do not establish hosted transaction-end policy or gateway role mapping.

**Local acceptance:** fifteen focused tests cover admission/response bounds, real sockets, redirects/status/truncation/trickle timeout, cancellation/original-ID readback, busy/shutdown, retained cleanup/client closure and synchronous decoding beyond deadline. The full worker regression passed **1,416 tests with 18 expected skips** before the last three focused cleanup/decode cases were added; all fifteen final focused cases pass. Nine additional real PostgREST **14.5** tests (matching hosted metadata) exercise JWT/audience/expiry/roles, schema/hidden helper/direct table write denial, two-owner reads, real late rollback, independent commit readback, transaction-end override policy and actual v5 controller bootstrap/tick/stop/contiguous outbox ACKs. The full isolated PostgreSQL/PostgREST regression passes **125 tests**, including those nine HTTP/database cases, in 404.069 seconds. The final focused HTTP fixture rerun also passes after ownership/binding verification was tightened.

The HTTP fixture explicitly acquired the official 14.5 image to match hosted metadata, pins its local immutable ID, and creates/removes only labeled owned resources. Docker 29 disables publishing on internal networks; the fixture uses its own bridge with outbound IP masquerading disabled and one exclusive loopback HTTP port. PostgreSQL has no host port; its network HBA permits only the fixture authenticator/subnet. This is not a general egress firewall or a model of Supabase's gateway. No application credentials/env files, unrelated containers, shared settings or other agent processes are used. SQL-only fixtures retain no network.

**Material findings:** forced PostgREST rollback can return 200 even with requested `tx=commit`; independent committed journal/projection evidence is mandatory before activation. A privileged service-role RPC can accept another valid owner argument: client owner pinning does not authenticate a user against credential compromise. Custom worker privilege design, complete object-level revocation, hosted schema-cache/JWT/transaction acceptance and source/remote lease/relay timing remain D3/A3 gates.

**MVP planning:** [MVP-READINESS.md](MVP-READINESS.md) and TODO now name the ordered paper critical path and LIVE-01…07. The first supervised pilot uses two EMA genes/eight candidates/one SOL/USD reference market/one window/one replacement, with explicit quote/time/command limits and retained holdings on stop. Automatic restoration is separate from safe interrupted-state handling. Continuous multi-window operation needs compact/versioned checkpoints and broader capacity/retention acceptance. Real trading needs empirical strategy acceptance, custody/independent risk, atomic-token/transaction validation, durable on-chain uncertainty, actual wallet accounting, fault/shadow acceptance and a separately authorized tiny canary. No extra genes or optimizer library rewrite is required for this narrow MVP. Research remains explicit and dependency-specific.

**Release/rollback:** this increment changes no database migration, service selection or live execution path. Review and push only the focused files via the pinned GitHub helper; verify exact preview source/team/project/repository/author before the authorized merge, then verify the exact production merge/deployment and four read-only smokes. Rollback is a reviewed revert of this inert code/documentation increment; it needs no database rollback. Preserve the existing historical migration edit and untracked files.

## 50. DB-03A2D3A — atomic curated history, durable relay and archive rehearsal

**Target verification:** GitHub `TOOTRJ/TheDashboard` / `1141090963`, Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` / team `team_8iNNxiNjrOseD4gdSCHkQEzF`, and Supabase `The Dashboard` / `fxpxsciltakyypunglzr` / organization `cqfnnaunmupdyobkyqfo` matched independently before work. The new sequential read-only inventory uses a repeatable-read/read-only transaction with finite statement/lock limits. Counts remain 8 stopped colonies, 497 probes, 807 trades and 9,837 snapshots, with no new owner/run mismatch. Legacy missing metrics/execution/parent evidence and orphan-from-colony histories remain as recorded in the prior snapshot; a single production owner is not a two-owner isolation test. The fourteen migration versions and absent durability schema are unchanged.

**Implemented boundary:** `002_read_projections.sql` is an isolated fresh-only contract, outside migrations/startup. A journal trigger materializes indexed owner/run/command/revision history in the economic transaction. Retirement cash is reconstructed before reserve transfer; terminal capital is distinct from current zero account cash and never counted twice. Removed members retain terminal versions and completed evaluation history. Last-observed final-member metrics are labelled explicitly, and absent fitness is not fabricated. Exact USD-reference strings, uncalibrated costs, sampling/source/version fields remain separate from legacy floats and on-chain token accounting. [Complete read/relay/archive contract](services/vonneumann/READ-PROJECTION-CONTRACT.md).

**Read/relay/archive:** JWT-derived owner predicates, bounded pinned-revision pages and private core/projection/helper grants are tested. Identity-only durable acceptance reads the committed original outbox event, allocates a monotonic relay sequence under the run lock, deduplicates repeats and gates economic ACK. A separate replay cutoff prevents delayed events from appearing below a browser cursor. The injected publisher validates exact receipts before allowing coordinator ACK. Non-destructive run archive requires a known complete stopped v4/v5 checkpoint; it retains open holdings and the core's reconciliation warning. Orderly stop sets that warning too, so archive eligibility does not silently clear it. Interrupted/uncertain runs remain ineligible. The unused browser bulk-delete helper is removed; the new RPC is not selected in production.

**Integration and limitations:** The actual v5 controller bootstraps, accepts a provider tick, stops, commits projections, accepts/ACKs relay events, reads owner history and archives through owned local PostgREST 14.5 with fake fixture JWTs. Two-owner/anon/privileged read denial is exercised locally. Pure browser adapters validate exact money/rational display, tagged scores, owner/version/currency, cursors, snapshot continuity and cancellation; they import no Supabase client and are not wired into existing UI. The fixture exhausted its 256 MiB tmpfs when retaining multiple unrelated dense traces; fixture-only reset between complete traces keeps the test bounded. This is not a production journal-retention policy or capacity proof.

**Validation:** 1,423 ordinary worker tests pass with 20 expected isolated-database skips; all 139 isolated PostgreSQL tests pass, including 11 PostgREST 14.5 cases. All 142 frontend tests pass; lint has zero errors and 33 existing warnings. The isolated Next.js production build and TypeScript compilation pass. Release evidence is recorded in the PR. Production build uses bundled Node 24.19.0, an isolated source/dependency copy and fake application configuration; no local/shared environment file is pulled or changed.

**Remaining:** D3B reviewed v5 forward DDL/object/grant manifest and legacy classification, D3C all direct-writer replacements plus compatible browser run discovery/detail/archive/event wiring, then DB-03A3 hosted migration/gateway/schema-cache/transaction-end/full-flow acceptance. Deep substantial research remains for custom economic/relay roles, inherited privilege closure, sample/legacy comparability, production retention/query/storage/lease costs and compact checkpoint dependencies. No hosted commands, migrations, legacy grant changes, worker launch or live trading occurred. Preserve the original historical migration edit and other agent artifacts. Code rollback for this inert slice requires no database rollback; eventual cutover rollback retains acknowledged history and never restores unfenced writers over v5 runs.


## 51. DB-03A2D3B1 — legacy write retirement, classification and installer evidence

**Verified read-only scope:** the dedicated GitHub helper confirms biggrizzly11/16749816 and TOOTRJ/TheDashboard/1141090963 with canonical origin. Supabase project metadata, local link and cached pooler identity match The Dashboard/fxpxsciltakyypunglzr/cqfnnaunmupdyobkyqfo. The new sequential repeatable-read/read-only inventory matches every prior catalog/count field, including fourteen migration versions and absent durability schema. No user-row IDs/configuration/genomes/credentials/function bodies were output. Production counts remain 8 stopped colonies, 497 probes/24 runs, 807 trades/17 unclosed records and 9,837 samples. A single production owner is not two-owner proof.

**New installation finding:** the additional [capability query](supabase/audits/vonneumann-owner-capabilities.sql) and [approved metadata](supabase/audits/2026-10-05-vonneumann-owner-capabilities.json) confirm the query runs as ordinary hosted postgres, which has CREATEROLE/BYPASSRLS but is not a superuser. It can use auth/auth.uid() and REFERENCES auth.users.id, but cannot grant those dependencies onward. vn_contract_owner is absent. API roles have no ADMIN memberships/CREATEROLE/CREATEDB/replication in the snapshot. Local superuser bootstrap therefore does not establish a viable hosted private-owner installation. B2 must prove the actual ownership/SET ROLE/constraint/auth dependency path without modifying managed auth grants or borrowing privileged credentials.

**Implemented isolated scope:** independently reviewed session-local catalog input, locked recheck, exact legacy table/column write retirement including REFERENCES/TRUNCATE/TRIGGER/MAINTAIN, and recomputed inherited/settable effective privileges. A changed catalog, indirect dependency, privileged/ADMIN/delegated grant path or surviving write aborts atomically. Shared role memberships and postgres/supabase_admin defaults remain intact. All legacy rows/definitions/RLS/SELECT and unrelated sentinel grants/rows are preserved. A hash-pinned [manifest](services/vonneumann/db-contract/legacy_retirement_manifest.json) explicitly declares rehearsal-only/nondeployable scope. [Full contract/research](services/vonneumann/LEGACY-WRITE-RETIREMENT.md).

**Classification:** authenticated JWT-derived owner/run summaries retain unfenced colony-backed and unmanaged/orphan/unbound history, unknown currency/sampling/execution/metrics/ancestry policy, unresolved relationships and unreconciled open records. No float-to-v5 hydration, fabricated parent/backfill or deletion occurs. All legacy archive eligibility remains false until a reviewed durable drain/reconciliation/evidence workflow exists. Saved stopped status or zero open records is insufficient. The 17 unclosed production records are not proof of current on-chain holdings.

**Acceptance:** all 25 focused real PostgreSQL tests pass in 30.019 seconds, with two owners/anon, actual role connections, authenticator SET ROLE, column/PUBLIC/nested maintenance grants, ADMIN/CREATEROLE/private-owner rejection, defaults/unrelated-object preservation, sequence/view/FK dependencies, catalog drift, late rollback, old-writer lock timeout and late writes after commit. A presentation rollback preserves evidence/denial. Actual v5 creation/bootstrap and eight-probe atomic projections coexist without a second legacy economic writer. The final manifest source hashes match the tested SQL. All 142 frontend tests pass. The ordinary worker regression ran 1,447 tests successfully in 308.310 seconds with 44 expected isolated-database skips; its discovery preceded the final additional sequence-dependency case, which passed in the final 25-case SQL run. No production build/schema change or worker startup is implied by these tests.

**Release gate:** dedicated Vercel CLI verification failed before returning target metadata under both the global runtime and isolated Node 24; the dedicated auth file was absent on inspection. Login to /Users/redjester/.config/vercel-dashboard-codex with VERCEL_TOKEN_STORAGE=file and no inherited Vercel token/org/project overrides was requested. No shared/default login, credential copy, global tool update, profile/team switch or unrelated-project operation is used as a fallback. On 2026-10-06 the user completed login to that exact profile. Fresh authenticated project/team metadata and non-interactive resolved checkout inspection match the Dashboard project ID/name, team ID/slug and GitHub repository ID. Dedicated GitHub user/repository and Supabase project/organization/local link also match. Release requires the reviewed exact-source READY preview, authorized merge of that head, exact-merge READY production and four read-only application smokes. Immutable release evidence belongs in the PR; PR44 remains the preceding verified production baseline.

**Next:** D3B2 v5-only forward DDL/object/grant/credential package under actual installer privileges, complete durable legacy evidence/archive policy and post-acknowledgment additive rollback; D3C selected single-authority service/browser flow; DB-03A3 hosted installation/gateway/schema-cache/transaction/full-flow acceptance. Deep substantial research remains for economic/relay role separation, indirect privilege closure, legacy/sample comparison, production lock/query/storage/source/lease/relay costs and compact checkpoint/retention dependencies. Parent D3B/D3/A3 and paper hosting remain open. Real signing/funding/swaps/trading are outside this increment. Historical migration SHA-256 remains a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc; other agent edits/artifacts are preserved.


## 52. DB-03A2D3B2A — hosted-like installer/Auth dependency proof

**Scope:** no hosted DDL, row/grant change, credential creation/rotation, shared profile change, migration or worker/trading launch. The preceding PR45 production deployment and four read-only checks were verified on 2026-10-06. Exact GitHub/Vercel/Supabase identities are reverified before this release's remote operations; immutable source/preview/merge/production evidence belongs in its PR. Preserve the historical migration SHA-256 a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc and other agent artifacts.

**Implemented proof:** the local fixture renames initdb's OID-10 bootstrap superuser, then creates and authenticates as a distinct actual NOSUPERUSER postgres login with the measured CREATEROLE/CREATEDB/BYPASSRLS/INHERIT attributes and non-grantable Auth usage/uid execution/id REFERENCES. A transaction creates the private NOLOGIN owner, PostgreSQL 17's separate noninheriting ADMIN-only/SET-only installer memberships, and an installer-owned fixed-search-path parameterless Auth uid bridge. The private owner cannot change the bridge, use managed Auth directly, acquire managed-role membership or grant bridge execution onward. The installer creates the Auth-FK run table using its existing permission, transfers ownership and removes temporary core-schema grants. The remaining economic/validator/projection SQL retains original semantics. [Contract and credential research](services/vonneumann/INSTALLER-BOUNDARY.md).

**Acceptance:** seventeen real isolated PostgreSQL cases pass, including all four v5 optimizer bootstraps and eight-probe atomic projections, two-owner/null-identity history denial, FK enforcement after handoff, direct API/owner denial, caller search-path and creator-setting handling, old bootstrap failure, stale-name rejection, unexpected function-default grant rejection, late atomic rollback and Auth-FK lock timeout. Auth owners/ACLs/column grants/uid body, API attributes/memberships, installer defaults and unrelated rows/grants remain unchanged. The source manifest pins 001/002/004; unique composition anchors reject drift. The ordinary worker regression ran 1,465 tests successfully in 231.112 seconds with 62 expected isolated-database skips; all 17 new SQL cases passed separately in 10.288 seconds. Python syntax, both isolated source manifests, whitespace and the protected historical migration hash are verified. No frontend/runtime/package code changes require additional frontend test runs. Immutable release results are recorded with the PR.

**Limitations and next priority:** this composes the isolated multi-version laboratory, not deployable v5-only DDL. It does not prove managed DDL hooks or hosted schema/gateway/transaction-end behavior. The bridge delegates auth.uid() and does not verify signatures or authenticate arbitrary SQL claims. Separate modern Supabase secret keys both map to service_role; credential isolation needs a proved custom-role/issuer or direct-database/broker design. Next B2 work extracts canonical v5-only dependencies/entrypoints and full object/signature/hash/grants, proves economic/relay credential separation, adds owner/run/original-ID/provenance-bound legacy drain/reconciliation/archive evidence/invalidation, then additive rollback after acknowledgment. Legacy classifier composition, D3C one-writer service/browser selection and A3 hosted application remain open. Deep research remains for indirect privilege closure, credential issuance/expiry and gateway feasibility, legacy evidence/sample comparability, compact checkpoints/retention and measured production timing/cost. Code rollback for this inert release requires only a reviewed revert; it is not the future post-acknowledgment database rollback.


## 53. DB-03A2D3B2B — canonical fresh v5 component and SQL capability separation

**Scope:** fresh GitHub helper and dedicated Vercel/Supabase identity metadata match only TOOTRJ/TheDashboard/1141090963, the-dashboard/prj_wFUe9k9USVreOQcmQKNWRAVsx5fH/team_8iNNxiNjrOseD4gdSCHkQEzF and The Dashboard/fxpxsciltakyypunglzr/cqfnnaunmupdyobkyqfo. No hosted database DDL, credential or application configuration changes.

**Implementation:** explicit v5-only creation/commit/journal/outbox admission; hash-pinned shared dependency extraction; committed SQL/manifest for 72 functions and 18 fresh tables plus domain/indexes/triggers. Raw policies are omitted; economic and relay RPCs use separate inert NOLOGIN roles, authenticated users receive only three owner-scoped curated functions, and service_role has no fresh capability. Limited actual postgres installation uses the fixed Auth bridge/FK handoff; final ownership/body/search-path/grant/effective-authority checks fail closed. [Full contract and remaining research](services/vonneumann/CANONICAL-V5-PACKAGE.md).

**Validation:** five offline artifact/dependency checks and 31 real isolated PostgreSQL cases cover all four solver seed/protect/decide paths, provider/clock/history tampering, expiry/replay, controller lost acknowledgments/cancellation/pause/stop/finite runner, independent non-admin capability logins, owner/foreign/null history, relay acceptance/ACK/dedup, archive replay, exact inventory, source drift, stale role refusal, unexpected defaults, final/projection rollback and FK lock timeout. Ordinary regression and release evidence are recorded with the PR. The protected historical migration and other agent artifacts remain preserved. Frontend/runtime/package dependencies are unchanged.

**Remaining:** SQL permissions alone do not authenticate credentials or owner/run arguments; the current single-key HTTP adapter needs a separately proved economic/relay authentication/routing design. This is a fresh component manifest, not the full production package including durable legacy evidence, classifier/retirement composition, migration/catalog/history/overlap acceptance and additive post-acknowledgment rollback. D3C service/browser and A3 hosted full-flow/migration follow. Deep substantial research remains for credentials/indirect privileges, legacy exposure/sample comparability, retention/compact checkpoints and production timing/capacity/hosting. Code revert suffices for this inert release; no database rollback is required.


## 54. DB-03A2D3B2C1 — native session identity and owner/run authorization

**Scope:** fresh isolated-helper/dedicated-profile metadata verifies TOOTRJ/TheDashboard/1141090963/biggrizzly11, the-dashboard/prj_wFUe9k9USVreOQcmQKNWRAVsx5fH/team_8iNNxiNjrOseD4gdSCHkQEzF and The Dashboard/fxpxsciltakyypunglzr/cqfnnaunmupdyobkyqfo. No hosted DDL, credentials, Auth signing keys, server SSL setting, environment or runtime selection is changed. The worker remains unhosted. The protected historical migration hash and other agent artifacts are preserved.

**Implementation:** the unchanged canonical v5 package is composed offline with a private immutable role-OID/name/owner/run/capability/expiry issuance registry. All eight economic/relay functions check real SCRAM session identity, exactly one bounded non-admin capability and current binding at entry and every successful return. Expired writes allow only bounded original-ID readback; revocation is one-way and serializes with admitted transactions. Rotation issues a new principal rather than changing old scope. Late expiry rolls back create/batch journals, economics and projections. [Contract and primary-source research](services/vonneumann/NATIVE-SESSION-AUTH.md).

**Validation:** five offline artifact checks and twenty actual TLS/SCRAM PostgreSQL cases cover password/CA/hostname/plaintext failures, owner/run spoofing, capabilities/private/API/trust denial, role drift and activation, open-session expiry/revocation, lock serialization and stale snapshots, rotation/OID reuse, immutable scope, late create/batch rollback, real v5 bootstrap/relay/owner projections, limited-installer Auth/API/default/unrelated preservation, late installation rollback and namespace collision. The 31-case canonical suite is retained as a dependency regression. The ordinary worker regression passed all 1,526 discovered tests in 237.953 seconds with 113 expected isolated-database skips; the final five offline checks and twenty authentication database cases pass separately. Both late-effect cases use observed server barriers to prove execution reached the trigger before expiry. Immutable release results are recorded in the PR. No frontend/runtime dependency change requires another frontend build.

**Limits and next:** the actual hosted SSL policy, project CA, native-role authentication and network profile are not yet proved. PostgreSQL TLS statistics are redacted under switched/definer roles; no broad stats permission or extension is added to work around this. Direct TLS/SCRAM is the candidate profile; session pooling needs separate authentication/state/timeout proof. Checks define statement admission/final return, not exact WAL-commit expiry; held transactions can delay revocation. B2C2 must own async connections/transactions/commit uncertainty, strict exact JSON/results, cleanup/deadlines and original-ID reconciliation through the real controller/relay. Durable legacy evidence/archive invalidation, full migration/classifier/retirement composition/overlap/post-acknowledgment rollback, D3C/A3, timing, preview isolation and hosting remain. Deep substantial research is retained for network/pooler/TLS/credential lifetimes, connection and revocation latency, retention/checkpoints and source/lease/relay costs. Code revert suffices for this inert release; no production database rollback is required.


## 55. DB-03A2D3B2C2 — bounded native async SQL transport

**Verified targets:** the dedicated GitHub helper confirms biggrizzly11/16749816,
TOOTRJ/TheDashboard/1141090963 and push access. Fresh authenticated dedicated
Vercel metadata and the local pin match the-dashboard/prj_wFUe9k9USVreOQcmQKNWRAVsx5fH,
team_8iNNxiNjrOseD4gdSCHkQEzF and GitHub repository 1141090963. Supabase metadata
and explicit local link match The Dashboard/fxpxsciltakyypunglzr, organization
cqfnnaunmupdyobkyqfo. Identity verification uses only approved target metadata;
no other project data/configuration or shared credential/settings were changed.
PR48 merge c80bc7c1ee1676a9bf9c2bd93326f16d9ceec427 is the preceding verified baseline.

**Implemented:** explicitly injected inert Psycopg 3.3.6/binary transport pins the
Dashboard direct host/port/database, supplied private CA/verify-full, required
SCRAM/channel binding and separate economic/relay principals. Inherited PG
configuration fails closed; password, certificate/key and CRL defaults cannot
read shared home credentials. One fresh owned connection explicitly begins,
switches only its capability, binds one allowlisted RPC and validates capped raw
strict JSON before explicit confirmed COMMIT. No psql subprocess, pool, retries,
application environment lookup or startup selection. Cancellation and uncertain
commit replies retain original IDs and owned I/O/cleanup; late connections close
and pending/failed cleanup prevents reuse. [Complete contract, primary sources
and limits](services/vonneumann/NATIVE-SQL-TRANSPORT.md).

**Real finding:** an existing empty CRL directory enables OpenSSL CRL checking and
rejects a CA without a CRL. The tested implementation uses an explicitly absent
CRL file in its own private directory to suppress default home fallback; it does
not claim CRL validation. Hosted certificate/CA lifecycle and revocation policy
remain gated. This was found by actual TLS testing, not mocked driver behavior.

**Acceptance:** fourteen ordinary cases pass. Eight real CPython 3.12/Linux ARM64
Psycopg/libpq 18.6 cases execute beside the owned network-none PostgreSQL 17.6
fixture. The driver/container has no host mounts/ports, is nonroot/read-only with
bounded resources and uses a stdin-staged, hash-verified offline wheel install
and synthetic tmpfs credentials. Only DNS is patched to fixture loopback; actual
TLS/SCRAM, controller, repository, durable publisher, SQL and roles are exercised.
Independent observer connections prove complete bootstrap/exact fractional-price
paper tick/pause/reserved stop, eight latest probe projections, relay acceptance/
ACK/outbox drain, bad CA/password and server owner/run/capability denial. Fault
hooks around actual COMMIT prove lost reply/original-ID recovery without duplicate
commands/provider refetch, cancelled caller ownership, real SQL lock timeout,
pre-COMMIT rollback and recovery after a timed-out already committed reply. These
are controlled driver fault injections, not hosted packet-loss/pooler tests.

**Dependency/regression:** all existing 49 Python versions are preserved; two
matching driver packages bring both locks to 51 pins. Clean hash installations
pass on Darwin and Linux ARM64; pip check passes. Runtime/test pip-audit 2.10.1
scans report zero known vulnerabilities; native-library/SBOM/licensing review
remains for hosting. The ordinary worker regression reports **1,540 tests in
232.695 seconds, OK with 114 expected isolated-database skips**. The eight real
driver cases pass separately in 3.764 seconds (10.730 seconds including the host
wrapper/setup). SQL candidates/artifacts are unchanged; their ordinary drift
checks remain covered. No frontend runtime file/package changed. Whitespace and
protected historical migration hash checks pass. Both fixture containers are
removed by exact ownership-label checks. Shared/global tools/processes and the
other agent's files are preserved.

**Next:** B2C3 read-only hosted CA/SSL/network/authentication facts and scoped
credential validation/storage/expiry/rotation/revocation/rollback plan; then B2
durable legacy writer drain/reconciliation/archive evidence and invalidation,
full canonical/auth/retirement/classifier/history/overlap and additive rollback
retaining acknowledged commands. D3C/A3 complete service/browser cutover, measured
provider/DB/lease/relay timing/quotas, preview isolation and HOST packaging/hosting
still precede a supervised paper launch. Deep substantial research remains for
direct IPv6 versus session pooler identity/TLS/channel binding/queue bounds,
connection/handshake capacity, native dependency/CA maintenance and held-transaction
revocation latency. No hosted SQL, native credential provisioning, migration,
worker launch or live transaction occurs in this slice. B2/D3/A3 remain open.

**Release/rollback:** reviewed focused PR via the Dashboard helper, exact-source
READY preview, authorized exact-head merge, then exact-merge READY production,
four bounded read-only smokes and scoped error logs. Immutable evidence belongs
in the PR. A reviewed code revert is sufficient; no database/credential rollback
is needed for this inert increment. No live funding, signing, swaps or trading.

## 56. DB-03A2D3B2C3A — hosted metadata, TLS-only preflight and hosting correction

**Exact targets:** fresh dedicated helper/profile metadata and local pins match
TOOTRJ/TheDashboard/1141090963/biggrizzly11, the-dashboard/prj_wFUe9k9USVreOQcmQKNWRAVsx5fH/
team_8iNNxiNjrOseD4gdSCHkQEzF and The Dashboard/fxpxsciltakyypunglzr/
cqfnnaunmupdyobkyqfo. CLI resolved-project inspection also matches the project ID,
name and owner slug; authenticated API metadata independently supplies the
immutable team/repository IDs. No other project's contents, shared credentials,
settings, processes or tools are changed. Prior baseline is PR49 merge
9508e6bed91344d5e60e5c7d2321f23a4ea3bb8f.

**Read-only facts:** identity-pinned experimental SSL GET reports enforcement off
and successfully applied configuration. A bounded read-only/repeatable-read SQL
query reports PostgreSQL 17.6, TLS capability/minimum 1.2, a management backend
TLS 1.3/SCRAM session, max_connections 60/3 superuser reserved, default SCRAM
password encryption, absent fresh schemas/roles/native principals and the same
fourteen migrations. The management backend is not an actual worker direct
session or CA/channel-binding proof. Exact-host DNS gives one public AAAA/no A;
local macOS getaddrinfo fails and explicit IPv6 TCP reports network unavailable.
No login, SQL or TLS bypass is attempted by this network check. Approved metadata
only is committed; no database rows, role password hashes, unrestricted settings
or credential values are captured. [Detailed evidence and limits](services/vonneumann/HOSTED-NATIVE-PREFLIGHT.md).

**Implementation:** explicit operator tool inspects only supplied public CA PEM
with size/content/CA/usage/duplicate/expiry checks and hashes. Its opt-in probe
requires the reviewed file hash, pins the exact direct database host, owns one
finite child, verifies hostname/CA/TLS and sends only SSLRequest. No database
StartupMessage, authentication, SQL, fallback, environment credentials or default
trust store. Eleven offline cases include real loopback TLS, wrong CA/hostname,
plaintext refusal, safe errors and child timeout/strict output bounds. Full worker
regression passes **1,551 tests in 359.221 seconds** with **114 expected isolated
database skips**; the final eleven focused cases and isolated CLI synthetic-CA
inspection pass separately after the small error-sanitization adjustment. Startup,
SQL candidate/migrations, Python dependencies and frontend behavior are unchanged.

**Hosting and credential plan:** Railway's newly documented per-service outbound
IPv6 makes it the leading candidate; selected account/service/region/actual IPv6,
capacity, drain and budget still need acceptance. Render's IPv4 path needs separate
proof, not automatic pooler or paid-add-on selection. Current limited-worker tests
use disposable administrator issuance; they do not prove hosted-like postgres
issuance/grant/registry/revocation. C3B now makes that gap explicit. The private
pair storage/finite expiry/recovery/new-principal rotation/revocation/canary and
additive rollback plan retains unresolved original commands and acknowledged
history. Server SSL enforcement off fails the planned TLS-only provisioning gate;
client inventory and reviewed reboot/maintenance plan precede any setting change.

**Remaining:** C3 stays open for project CA provenance/validity, actual worker-host
network and limited issuer/native-session/channel-binding acceptance. No hosting
account/service is created, no native credential provisioned, no hosted DDL,
server SSL toggle, environment or startup path changed. The worker remains
unhosted. Follow C3 with durable legacy evidence/archive invalidation and complete
forward composition/catalog/history/overlap/additive rollback, then D3C/A3,
actual source/lease/relay timing/quotas, preview isolation and HOST acceptance.
Deep substantial research remains explicit for CA/revocation/native-library
SBOM/security/license, connection/COMMIT/relay capacity and finite revocation
latency. For this inert increment, rollback is a reviewed code revert only.

**Release:** reviewed Dashboard PR, exact-source READY preview, authorized
exact-head merge and exact-merge READY production/read-only smoke/error scan.
Immutable source/merge/deployment and final regression evidence are recorded in
the PR; no live funding/signing/swaps/trading are included.

## 57. Certificate intake and Railway account setup — 2026-10-07

**Scope:** fresh exact GitHub/Vercel/Supabase identity metadata matches all existing
Dashboard allowlisted targets. The authenticated Railway dashboard is inspected
read-only: Red Jester's Projects, Trial, 30 days or $5 left, zero projects, candidate
workspace f3fcd4b2-e424-4c6b-ac33-91196ccc96e1 from the visible project-creation link.
No workspace/project/service/integration, plan, billing, secret or account setting
is changed; no Railway project target or CLI/API authentication is established.
The Trial badge does not prove Full Trial outbound networking.

**Local action:** add root `/ssl/` to `.gitignore`; actual CRT and nested/future
CRT/key paths match the rule, and `git ls-files -- ssl` is empty. The supplied
`ssl/prod-ca-2021.crt` passes the existing offline inspector: one valid CA,
2021-04-28T10:56:53Z through 2031-04-26T10:56:53Z. Exact PEM SHA-256 is
700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7; DER SHA-256 is
807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa.
Only hashes/dates are recorded; certificate bytes remain local. User provenance
follows the prior exact-project download instruction, not an independently
observed download or peer handshake. A fresh bounded fixed-host TLS-only probe
reports dns_failed, with no database login or SQL. Actual worker-host IPv6/TLS,
limited native issuance and scoped authentication remain C3B gates.

**Validation/release:** ignore matching/tracked-file absence, offline certificate
inspection and whitespace checks suffice for this ignore/documentation-only
change; runtime/dependency/SQL/frontend code is unchanged. Preserve the protected
historical migration and unrelated drafts. Use a reviewed Dashboard PR and exact
preview/merge/production verification under standing release authorization;
immutable evidence belongs in the PR. A code revert is the rollback; no hosted
migration, credential or worker launch is involved.

**Release blocker observed later in this intake:** PR #51 is open on the verified
Dashboard repository. The initial immutable Vercel target read succeeded, but
subsequent isolated CLI checks failed and metadata-only inspection confirmed the
dedicated `/Users/redjester/.config/vercel-dashboard-codex/auth.json` is absent.
No shared/default credential was used or copied. **Resolved after the user's
dedicated-profile login:** exact target/source preview checks passed and PR #51
merged as 188d31014fe7425a5c602fb0d23892759a7150f4. Production
dpl_DY6TjaNrCWn7QWDcuDbvFtbULvzP is READY, serves the-dashboard-chi.vercel.app,
passes all four bounded read-only checks and returned zero scoped error records.
Immutable release evidence is in PR #51. No Railway configuration, database
mutation or worker launch occurred.

## 58. DB-03A2D3B2C3B1 — limited native issuer proof offline

**Baseline/targets:** PR #51 is the reviewed baseline above. Fresh dedicated CLI
context and immutable metadata match the-dashboard/prj_wFUe9k9USVreOQcmQKNWRAVsx5fH/
team_8iNNxiNjrOseD4gdSCHkQEzF/orderoftheredjester, TOOTRJ/TheDashboard/1141090963/
biggrizzly11/16749816 and The Dashboard/fxpxsciltakyypunglzr/cqfnnaunmupdyobkyqfo.
Only allowed identity metadata is inspected remotely. Unrelated projects,
credentials, tools and processes and the protected historical migration remain
unchanged. No hosting or linked SQL mutation is performed.

**Scope:** inert, hash-pinned isolated templates compose with unchanged C1 native
auth SQL. The actual fixture postgres login is non-superuser with measured
Dashboard-like privileges; administrator connections only seed/observe/inject.
Exact identity/catalog/membership checks precede pair creation. Private table
resolution and registry insertion use the reviewed explicit owner switch rather
than extra schema/Auth grants. One bounded transaction creates two NOLOGIN
principals, SET-only disjoint capabilities, immutable DB-clock owner/run/OID/
issuance bindings and finite deadlines, validates and publishes LOGIN at COMMIT.
Caller creator/password settings restore. Synthetic SCRAM verifiers avoid
plaintext password statements; secrets/known verifiers stay in memory/stdin/owned
private tmpfs and are redacted from returned diagnostics, never Git or reports.

**Revocation/uncertainty:** retained scope/OIDs suffice without old passwords.
Ordered row locks, one-way binding updates and NOLOGIN are atomic; timeout is
failure, not partial success. Post-DDL OID/name revalidation rolls back an actual
concurrent name replacement, and real DDL-lock acceptance protects the final
check through COMMIT. Existing unadmitted sessions fail the binding guard;
admitted work is not preempted. Fresh immutable rotation retains original command
readback. A reply lost after issuance COMMIT retains the exact pair and refuses
resubmission; no fresh-pair automatic retry or compensating economics.
[Contract, source boundary and deeper research](services/vonneumann/NATIVE-ISSUER-REHEARSAL.md).

**Validation:** worker discovery passes **1,596 tests in 258.303 seconds**, with
**152 expected opt-in database skips**. Explicit issuer/native-auth/canonical-v5/
installer regression passes **106 real PostgreSQL cases in 174.743 seconds**.
After the final secret-independent scope refactor, **seven ordinary cases** and
the complete **38-case issuer suite in 44.510 seconds** pass separately. The
existing eight real Linux native transport cases pass in 3.061 seconds inside
their owned driver container (8.422 seconds including setup/outer test); they
remain a separate dependency check using the older fixture issuer. Immutable
release evidence belongs in the PR. No runtime,
dependency lock, canonical/native-auth package, frontend or migration is changed.

**Remaining/release:** only C3B1 closes. C3B requires actual managed issuer and
selected host IPv6/project-CA/TLS/native canaries, gated secret injection and
client/SSL-maintenance review. B2 legacy drain/reconciliation/archive evidence and
invalidation, full composition/history/catalog/overlap and additive post-ACK
rollback remain before D3C/A3 selection/cutover. Provider/lease/relay timing and
quotas, preview isolation and hosting/image/capacity/drain gates precede paper
launch. Deep substantial research remains for issuer transport/SCRAM/logging/
uncertainty, role/registry/held-transaction lock tails, rotation/expiry operations,
managed hooks, CA/native maintenance and aggregate capacity. Reviewed exact-source
READY preview, authorized exact-head merge, exact-merge READY production and four
read-only smokes/scoped error scan remain the release procedure. A code revert is
the rollback for this inert slice; no hosted credential/object cleanup or live
funding/signing/swaps/trading occurs.


## 59. DB-03A2D3B2D1 — durable legacy evidence/archive rehearsal

**Scope:** inert component only, outside migrations and startup. Exact Dashboard GitHub/Vercel/Supabase project and owner identities are reverified before release. No hosted DB mutation, grant/role/credential creation, Railway service/billing/integration, worker activation or real trade is performed. Preserve the historical migration SHA-256 a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc and unrelated artifacts. Immutable release source/preview/merge/production evidence belongs in the PR.

**Change:** [LEGACY-EVIDENCE-CONTRACT.md](services/vonneumann/LEGACY-EVIDENCE-CONTRACT.md) and a deterministic private five-table/nineteen-function component retain immutable owner/run/legacy-provenance-bound review, explicit invalidation and archive request receipts. Separate nonprivileged attestor capability validates finite writer inventory/drain receipts, exact open-record coverage plus external exposure, UTC chronology and <=24-hour validity. Digests preserve evidence identity; they do not prove an external process exited or authenticate the referenced files. Resolved/retained/unknown-retained exposure remains legacy evidence with live holdings/restoration unverified. Owner-only status/history and non-destructive archive never delete rows, liquidate, recalculate floats or introduce v5 authority.

**Limited-installer findings:** SELECT cannot acquire SHARE locks, and preserved public RLS calls auth.uid() directly, which the private owner cannot use under the captured nongrantable managed Auth dependencies. Fixed installer-owned lock/aggregate helpers and a bounded classifier under existing postgres authority avoid adding managed Auth grants or legacy DML/MAINTAIN to the private owner. Explicit SET owner and temporary installation grants are necessary; the fixture reproduced permission errors until these transitions were correct. Every temporary schema/function permission is revoked before commit.

**Invalidation/concurrency:** five ALWAYS AFTER STATEMENT triggers atomically increment a conservative global revision and append DML/TRUNCATE audit evidence, including zero-row, replica-mode and other-owner writes. Restoring previous values does not restore approval; rolled-back writes do not invalidate. Fixed-order legacy SHARE locks then a private serialization row prevent data change between snapshot/archive validation and commit. Calls require read-committed, already-set <=500 ms lock and <=8 s nonzero statement limits; owned clients have finite outer deadlines. Catalog/body/ACL/policy/capability drift fails closed. Reviews/archives replay identical original receipts after lost replies or invalidation without renewing eligibility. Current archive status separates recorded history from valid hiding. Unobserved reverted administrator changes are not automatically proved or permanently detected; operational withdrawal needs an explicit immutable invalidation.

**Validation:** the evidence/retirement/canonical dependency run passed all 89 real PostgreSQL cases in 128.267 seconds (33 evidence + 25 retirement + 31 canonical). After the final unexpected-default privilege check, all 34 focused evidence cases passed in 21.839 seconds. Three ordinary artifact/dependency checks pass. The full ordinary worker suite passed 1,632 tests in 240.417 seconds with 185 expected database skips; its discovery preceded the last added isolated SQL case, which passed in the final focused run. Final manifests match the tested sources. Relevant bounds/owner/rollback/role-drift/race acceptance is executable; frontend files and selected service behavior are unchanged. No frontend/runtime/package or historical migration change is included. The complete installation rollback test preserves original grants/rows/catalog and leaves no partial evidence schema/role; it is not the future post-acknowledgment additive rollback.

**Next:** B2D2 complete object/grant/forward composition, independently reviewed migration/catalog/committed postconditions, overlap and additive rollback after v5 acknowledgment; C3B managed issuer/project-CA/selected-host IPv6/native canaries; D3C one-writer service/browser flow then A3 application/full-flow acceptance. Railway stays unhosted. Deep substantial research remains for external inventory/receipt/wallet/transaction authenticity, managed attestor lifetime/scope/revocation, permanent DDL/grant audit/regrant semantics, indirect privilege closure, evidence/checkpoint retention and real query/lock/commit/storage/multi-owner capacity. No user account action is needed for this offline slice.


## 60. DB-03A2D3B2D2 — complete forward candidate and additive retirement

**Scope:** complete offline candidate only, not production SQL application or worker activation. Exact Dashboard GitHub/Vercel/Supabase project identities are reverified before the authorized PR/merge/release. The existing historical migration edit remains untouched at SHA-256 a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc. Railway remains signed in to Red Jester's Projects, Trial, zero projects; no account billing/credentials/service/integration is changed by this section. The user has requested all five next priorities, so service/browser, hosted acceptance, actual migration and bounded paper pilot remain active follow-on work.

**Change:** [FORWARD-CUTOVER-CONTRACT.md](services/vonneumann/FORWARD-CUTOVER-CONTRACT.md) defines one digest-pinned native v5/legacy/evidence transaction, independently reviewed target/migration/catalog inputs, closed release admission and post-COMMIT checks. Twenty existing dependencies stay unchanged. Final inventory: 97 function signatures/body and DDL hashes/owners/execute roles; 26 table definitions plus indexes/triggers/domain; complete private catalog snapshot and retained installation review. The metadata oracle includes no ledger records or password/verifier data. No native login is issued by installation. Actual measured non-superuser installer authority remains required; no managed Auth grants are added.

**Atomicity/rollback:** migration history SHARE lock precedes fixed-order ACCESS EXCLUSIVE legacy locks; changed version/name/statements digests, target/release or catalog require new independent review. Late failure rolls back all fresh objects and legacy revocation. The private admission state is initially closed, opens only through a bounded original-ID operator receipt and retires one-way. Shared admission locks hold through each create/heartbeat/batch transaction; retirement cannot acknowledge ahead of admitted writes. Retirement preserves economic state, journals/projections/engine checkpoints, relay/outbox, bindings and legacy evidence, with no old grant restoration or liquidation. Original get_command and relay drain remain available; actual lease expiry may conservatively mark interrupted/reconciliation-required. Current metadata drift fails closed, but unobserved reverted privileged DCL is not permanent history.

**Validation:** 39 real isolated PostgreSQL cases plus two deterministic artifact checks pass in 49.668 seconds, using actual limited postgres and native TLS/SCRAM identities. This includes all four real solver sequences, complete install/post-COMMIT checks, changed migration statements under the same version, wrong/missing review, overlapping old writers, late atomic failure, closed/retired writes, retained original-ID readback and relay, safe expiry interruption, archive retention, transition replay/conflicts, timeout/cancellation rollback and catalogue/privilege drift. Two inherited post-effect expiry tests explicitly review their synthetic sleep-trigger catalog; production has no such review bypass. The full ordinary worker suite passed 1,674 tests in 240.501 seconds with 225 expected isolated-database skips. Immutable source/preview/merge/production release evidence is recorded in the PR. No application/frontend/runtime/dependency selection changes are included.

**Remaining acceptance:** actual managed issuer/CA/SCRAM and selected-host outbound IPv6, D3C one authoritative service and compatible browser, A3 reviewed complete migration/history update/uncertain commit checks, measured provider/lease/relay quotas and drain tails, Railway packaging/secrets/origins/security, and the eight-candidate/two-EMA/one-window paper pilot. No live wallet signing/funding/swap is authorized. Research current metadata-check CPU and storage/connection cost, managed privileged wrapper closure, concurrent administrator grant history, bounded retention/compact checkpoints and trusted external legacy drain/exposure evidence before claiming those boundaries complete.


## 61. D3C paper service/browser preparation and HOST-02A image

**Targets and isolation:** baseline PR54 source `45806fc4c6d98164a3f84a7fa05e622046b24a1d`, merge `5cbcf870f532a1731a4a7c8724100d3a1beb19c9`, exact READY preview `dpl_8t5kehG25ewNsQwP5fpFFtDiA5K7` and production `dpl_7xUDyAnpRDpyLRuqTmGTMvAZnYng` passed the four read-only smokes and scoped error scan. Dashboard repository/project/owner pins are unchanged. The historical migration SHA-256 `a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc`, `.claude` and unrelated files/processes/shared credentials are preserved. No Supabase mutation, native issuance, API schema exposure or active worker is performed.

**Railway:** the private empty `The Dashboard Worker` project `38facb49-4de9-4d66-85aa-2861e0306dcf` is under `Red Jester's Projects`/`f3fcd4b2-e424-4c6b-ac33-91196ccc96e1`, production environment `9bbe52c6-2305-467a-bf39-8d5e1a98e4e4`. UI identity/name/private status were confirmed. No service/deployment/region/secrets/Git integration or billing change exists. The user approved a $20/month ceiling for the initial pilot; subscription and account-wide settings remain user-managed. Scoped project-token API verification is pending. The helper reads only ignored `ssl/railway-project-token.txt`, refuses symlinks/mismatched scope/owner/name, redacts responses and has no mutation or shared CLI context. Four offline identity/denial tests pass. [Setup, verified IDs and remaining gates](RAILWAY-SETUP.md).

**Service:** a new closed-by-default ASGI entrypoint is the sole new selected authority. Explicit private inputs construct the native economic/relay pair and exact v5 owner/controller/finite runner. HTTP tasks do not own the pilot; start latches before scheduling, lost acknowledgment settles only the original command, stop uses a separately reserved ID and retains holdings. A new process cannot adopt the old run. Broad Supabase writer/secret keys and Railway operator tokens are rejected in active runtime; dotenv remains disabled. Public health has no external side effect; authenticated status/controls and bounded streamed JSON controls permit only the configured owner and exact production browser origin. Legacy EventPersister/CRUD/status/risk writers are absent from this selected entrypoint. [Full configuration/behavior/limits](services/vonneumann/PAPER-SERVICE-CONTRACT.md).

**Browser/database overlay:** explicit `NEXT_PUBLIC_VN_SERVICE_MODE=paper-v5` selects the new actual view, remaining disabled in current production configuration. Owner discovery/details, exact USD balances/trades, completed/aborted evaluation scores, legacy diagnostics, original-ID controls/archive and contiguous durable replay are wired. Every detail kind pins one revision; token/selection/disposal retire old reads/control replies. Worker failure does not block committed history, and failed refresh retains an explicitly stale last complete snapshot. The independently hashed `browser.sql` adds authenticated-owner-only bounded discovery and an index to the complete package. Final inventory is **98 functions/26 tables**, release digest `5ba175e3c3f56fdbae0ae95a0573e1bc7e93ec0df30390bc8daabfc08cf23924`, package SHA-256 `05bf9bfab224b693f776edcf356ba57617448607f3ebe5d86d639b7115538fd1`; admission remains closed and production application unavailable. The original PR54's 97-function inventory is its historical baseline, not the new artifact count.

**Validation:** full worker discovery passed **1,683 tests in 358.717 seconds**, with **227 expected isolated-SQL skips**. Separate complete forward/native SQL acceptance covers 39 cases; two new actual TLS/SCRAM HTTP/database flow cases cover repeated start, lost-create settlement, restart refusal, real reserved stop, owner discovery/projections/relay and archive readback. Provider responses/Auth identity are synthetic. Frontend regressions, TypeScript/lint and isolated production builds use fake configuration only. Actual browser fixture verifies start/stop/archive/discovery/legacy diagnostics with no console warnings/errors; control/read interruption and owner/cursor/revision/event/precise display cases are offline regressions. Immutable final test/release counts belong in the PR.

**Image:** pinned official Python 3.12.14 Bookworm slim amd64 leaf, hash-required binary dependencies and deny-by-default source context. The built image `sha256:38ebb2bf9e9625230d603b3f160840ffd645446b20e0a41d3432e0d417fc76be` ran UID/GID10001 with network none/read-only root, no env/ssl/tests/agent/cache files, health200/status401/legacy404/docs404. Closed startup 6.739 seconds under local arm64 emulation; SIGTERM completed lifespan/server shutdown in 0.230 seconds. Uvicorn intentionally re-raises SIGTERM: expected exit143, not exit0. Only owned containers/server were stopped; local dev hit EMFILE and was replaced by a production test server without changing system watcher limits. These are closed-local canaries, not hosted resource percentiles or active-run drain acceptance.

**Remaining:** C3B actual IPv6/project-CA/managed issuer/native canaries, A3 independently reviewed exact-target/history/catalog/migration and owner-only API exposure, hosted two-user/expiry/revocation/interruption/overlap, actual provider/SQL/COMMIT/relay/lease/quota/resource/cost evidence, then HOST-07 finite paper pilot. D3C/HOST-02A preparation closes; A3/C3B/HOST parents remain open. Reverting code is sufficient only before DB/service activation. After acknowledged commands, retire admission under the original reviewed ID and retain every economic/history record; do not restore the legacy writer or drop schemas. Further deep and substantial research remains for remote tail latency/source semantics, shared credits/billing, managed hooks, issuer/CA/native maintenance, interrupted exposure and retention/compact multi-window checkpoints.

**Final rerun:** 50 combined real forward/native SQL, HTTP service and artifact cases pass in 91.068 seconds; 155 complete frontend regressions pass. TypeScript, isolated Next.js production build, focused changed-file lint and diff checks pass. Four separate Railway helper scope/identity denial tests pass offline. Exact target metadata is freshly reverified for GitHub/Vercel/Supabase. Final source-preview/merge-production evidence is recorded in the implementation PR.

**Subsequent account observation:** the Railway dashboard now visibly shows Hobby for Red Jester's Projects and the exact The Dashboard Worker project with no services. This was a read-only observation; Codex made no subscription/billing change. The production-scoped token and actual service/network/credential gates remain pending.

## 62. Railway closed host and selected-project IPv6/CA acceptance — 2026-10-07

**Exact targets:** dedicated GitHub verification matches biggrizzly11/16749816 and TOOTRJ/TheDashboard/1141090963; Vercel matches the-dashboard/prj_wFUe9k9USVreOQcmQKNWRAVsx5fH under team_8iNNxiNjrOseD4gdSCHkQEzF; Supabase matches The Dashboard/fxpxsciltakyypunglzr/cqfnnaunmupdyobkyqfo and the local management link. Railway token scope, actual project/environment names and workspace match The Dashboard Worker/38facb49-4de9-4d66-85aa-2861e0306dcf, production/9bbe52c6-2305-467a-bf39-8d5e1a98e4e4 and Red Jester's Projects/f3fcd4b2-e424-4c6b-ac33-91196ccc96e1. The new service is dashboard-paper-worker/8e78ad4b-1d8f-43e7-898a-3882ac5053d7. Both private token copies agree; the helper reads only the owned mode-0600 ignored token file. No values are output.

**Hosted source and isolation:** successful closed deployment d2946105-6ed6-4adc-bf63-23adab188c4a uses reviewed source 9837eb1af2a226b5ee4aa46a0f07731783216306, 94 allowlisted immutable files/1,179,683 bytes, normalized export manifest 3ebb7c046ca05b39b6937637d4bc0426d23d2bb9decf90b622cd4671343346c1. [Approved image digest/settings/proof](supabase/audits/2026-10-07-railway-closed-host.json). The official temporary CLI 5.63.4 archive matches SHA-256 0578c42c397c73c08d9adb2130b0ed9a376b80a972c51ba824d893ee0e71463a. Project-token child environment and explicit IDs avoid shared OAuth refresh/login/link; automatic updates/skills/telemetry are disabled and a macOS child sandbox denies shared Railway/SSH/Codex/Claude/config writes. No account SSH key registration is used. First FAILED deployment 6449485c-a651-4754-be1e-5c23816f8cfc caught private exported modes retained by Docker COPY before networking. Corrected non-root image imports and actual deployment pass; the exporter normalizes child directories/files while retaining a private staging root. The explicit application User-Agent fixes the default Python header's 403. Nine focused offline scoping/export/transport tests pass, including strict umask/exclusion and original failed-canary reconciliation before retry.

**Applied service:** Dockerfile build, one us-west2 replica, 0.25 vCPU/500,000,000-byte limits, no sleep, restart NEVER, overlap0/drain30, health /health timeout60 and IPv6 are verified in exact service/deployment metadata. The runtime has only closed/dotenv flags and supplied public CA; no deployment token, database/provider secret, broad Supabase key or active paper run. Source export excludes env/ssl/tests/agent/cache files. Hosted HTTPS health200, unauthenticated status401, colonies/docs404 and foreign-Origin403 pass. Normal responses use no-store; the early foreign-Origin rejection lacks that header and HOST-05A records the repair. Public origin exists but Vercel's public v5 mode/origin selection remains unchanged.

**Actual network:** the finite probe runs in the deployed container before exec of the normal closed entrypoint. It reaches only db.fxpxsciltakyypunglzr.supabase.co:5432 over IPv6, verifies supplied CA PEM SHA-256 700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7 and hostname, negotiates TLS1.3/256-bit cipher and observes peer DER SHA-256 ddb70cb3b060d7c891e519e86784225a3c3f8cea995ab32921dfe824dadacba5, expiry2031-03-09. Elapsed1.048s includes the finite Python child. No StartupMessage/authentication/SQL/channel-binding test is sent. Railway stores the JSON proof as structured log attributes; raw build/deployment logs are not emitted. This closes C3B2 reachability only, not native authentication or active controller acceptance.

**Fresh Supabase review:** bounded repeatable-read/read-only management SQL still observes PostgreSQL17.6, SCRAM postgres/TLS1.3, sixty connection slots, no new private owner/ledger/native principals and the same fourteen migrations. [Client-profile SQL](supabase/audits/vonneumann-hosted-client-profile.sql) groups only allowlisted role/application categories and transport counts, never raw SQL/addresses/application names. Managed/internal plaintext sessions are observations, not proof of an external application using plaintext. SSL-enforcement GET remains database=false/appliedSuccessfully=true. The pending user question inventories dormant/direct clients before a reviewed exact-database reboot; no enforcement setting is changed. [Forward metadata SQL](supabase/audits/vonneumann-forward-review.sql) captures the pinned legacy catalog and migration statement hashes using SELECTs with no temporary functions/persistent DDL. Independent metadata digests are migration fb48eb1305388e7daeaa702e461823901ededf513856ab79ca300cf054d9ebd7 and legacy711649d2fe9aa716a5f0ef90259db37d3471f1094038e6a65122cc0537ded643. Their Python canonical JSON encoding is explicitly different from PostgreSQL jsonb::text; never substitute these report hashes for the installer's expected JSON values/hash. Re-capture/review immediately before any later bounded install. No migration, credential issuance, API exposure, application rows or managed/shared settings changed.

**Budget and remaining work:** approved ceiling $20/month; nine minute-spaced closed samples peak at 0.055648256GB memory and 0.029888917vCPU, including startup/failed-canary samples. At current published rates the configured maximum CPU+RAM is about $10/month continuously, before egress/tax/provider costs; this is not an enforced account-total cap or active workload estimate. No billing change is made. Current Railway docs deprecate Config as Code with legacy support through 2026-12-01; HOST-02C requires project-only IaC review/migration while current deployment resolution is verified. Next: client inventory/SSL maintenance, actual managed installer/issuer and native canaries, A3 fresh target/catalog/history/backup/rollback/closed application/postflight, owner-only curated exposure/hosted two-user browser flow, real provider/SQL/COMMIT/relay/lease/quota/resource/interruption evidence, then finite two-gene/eight-candidate paper pilot. C3B/A3/HOST parents remain open. Live funding/signing/swaps/trading remain outside authorization. Deep research retains the actual tails/quota/managed hooks/CA-native maintenance/retention and checkpoint gates. Historical local migration and other agent files/processes/credentials are preserved.


## 63. Dashboard SSL maintenance and managed closed-install rehearsal — 2026-10-07

**Authorization/targets:** the user confirms no other known direct Dashboard DB clients and allows necessary Dashboard-only database/data migrations. Fresh scoped helpers verify GitHub repository/user, Vercel project/team/repository link and dedicated resolved profile, Supabase exact project/org/link and Railway exact project/workspace/environment/service token. No other project, shared login/settings or billing changes.

**Maintenance:** exact-project SSL enforcement switches from false to true, appliedSuccessfully=true, in 4.361s. Fresh read-only management session still uses SCRAM/TLS1.3; all fourteen migration records and original legacy catalog match after normalization. Four exact-production dashboard HTTP smokes pass. A private mode-0600 ignored snapshot retains 8 colonies, 497 probes, 807 trades, 9,837 fitness rows, zero generation-stat rows and migration source history; 5,305,685 bytes/SHA258a99bdf58f74bd0cb4a534ca5ebe7e01e0de812795809d0f3ba3d9177c9450. This is targeted recovery evidence, not a whole Auth/database backup.

**Actual findings/fixes:** managed postgres has REPLICATION, omitted in the earlier capture. Installer and issuer now require that observed profile; all new private/native/capability roles remain NOREPLICATION and nonadministrative. Auth uid already grants PUBLIC EXECUTE, but private owner lacks Auth schema USAGE: preserve the existing ACL and reject usable/delegable Auth access. The fixture now reproduces that combination, including real direct-call denial and PUBLIC schema-access rejection. Standalone review now uses pg_catalog/pg_temp to match the oracle's deparser; only schema qualification of FK/trigger text changes, and a real SQL test compares the independent complete results. These three findings are proved by failed/rolled-back managed canaries; no managed role/Auth grants are altered to bypass them.

**Managed acceptance:** complete 98-function/26-table install and limited issuer each pass with final ROLLBACK, in 2.877s and 2.014s respectively. Separate catalog reads/absence checks prove rollback. The deliberate production/history wrapper also passes rollback: schema/owner/version absent afterward. Final release6b9fceb02278ef9ca978743c43dd2d0dd2cacb49b310689c016fe58d65861fb1; package9eef84d2799b94b29bf1aadf9551efb3b59c3d9328deb60cd31abbe0af38eb7f. [Approved metadata](supabase/audits/2026-10-07-ssl-managed-rehearsal.json), [operation/recovery](SUPABASE-CUTOVER.md). These prove managed DDL/issuer hooks in rollback, not actual committed native authentication.

**Application preparation:** offline production.py binds independently completed review values to one new forward migration20261007010000, 25s transaction deadline, closed admission/zero runs/bindings and full postconditions. The Dashboard-only operator requires exact identities/applied SSL/closed host, fresh review, reviewed source merged in origin/main and private snapshot before submitting one file. It persists the original operation before application, inserts exact SQL into migration history in the same transaction, and reconciles uncertain replies with fresh read-only catalog/history/release sessions without automatic retries. Historical migration draft remains excluded; its SHAa62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc is preserved. No API exposure, live credential publication or worker activation in preparation.

**Validation:** 112 focused isolated PostgreSQL/component checks pass in82.483s after managed profile/Auth fixes; 38 real issuer cases passed in the preceding95-case run (the only later forward assertion correction is separately proved). Three additional real production-wrapper/capture cases pass in6.678s, covering atomic closed schema/history commit and late rollback. Six operator refusal/privacy/original-outcome tests pass. Final affected validation passes **152 database/component tests in209.028s and24 scoped operator tests**. Exact PR/deployment/application evidence is recorded on release. Deep substantial research remains for issuer secret/log transport/rotation, actual native tails, managed hook maintenance, provider shared quotas/billing, interruption exposure and retention/compact checkpoints.


## 64. Committed closed database cutover and bound native issuer preparation — 2026-10-07

PR57 merges source3fa55e4bb6fdd14dee74ea5aa2a06ea377efba3b into main0d42b5a528b71a963dd70c86152e000d9cb3936f. Exact-project preview dpl_CW51cSKAGkhc6M3EqVs38LWm1gEj and production dpl_xgpVhZaKfDfciVKD9jahPJVzYnBX are READY; all four production smokes pass before/after the closed DB application. Migration20261007010000/sourceSHA7b0c2d9578641de1d0b82204cc862338ce1e4f33da477070f4e4134eb6b39e36 commits schema and exact source history in the same bounded transaction. Fresh complete body/ACL/release verification and exact original-history equality pass. Admission remains closed at epoch0; no new run/credential/API exposure. Full private postflight compares all five legacy row arrays and all fourteen original history source arrays unchanged; history now has fifteen versions. [Approved acceptance](supabase/audits/2026-10-07-closed-install-acceptance.json).

Actual managed log_statement=ddl, pgaudit.log=none, duration/sample logging disabled and error parameters0. postgres cannot disable DDL logging. The documented Management API supports bound parameters; an actual harmless parameter canary passes, but bound multi-statements return400. The next reviewed issuer therefore installs a temporary private postgres-owned SECURITY INVOKER adapter, invokes one bound SELECT with precomputed SCRAM verifiers, then removes the adapter with RESTRICT. Its body reuses the pinned limited installer/revoker, requires the reviewed closed release and logging profile, sanitizes nested errors, and grants no extra privileges or API execution. Original scope/passwords/OIDs/outcome remain in owned mode0600 ignored files. No automatic reissue or replacement after uncertainty. [Operational contract](services/vonneumann/NATIVE-CREDENTIAL-OPERATIONS.md).

Four real bound-input PostgreSQL tests prove pair TLS/SCRAM authentication, limited invoker/API denial, collision rollback, absence of passwords/verifiers in server logs, catalog preservation and original-pair revocation/removal. Twenty-eight scoped operator tests and seven paper-service HTTP tests pass. The hosted canary and actual publication remain pending until the reviewed source is merged; admission/paper activation stay closed.


## 65. Actual original-pair native host acceptance and ordinary closed restoration — 2026-10-07

PR58 sourcefb5bc1990899c86995b58a646e742061b1d04fb5 merges as254fed49b90583bca411938d71c588ed93fba306. Exact Vercel productiondpl_H6zsfAU5Guc2na7FNAsQCw3z1znv is READY with four successful HTTP smokes. Allowlisted worker export has95 files/1,186,980bytes, manifest018a14bca7ab7be49ce0165be9599bbc6173b7b468df76f081888e8c2d62c024.

The original pair commits. Management read_only=True rejects the BEGIN/SET ROLE verification wrapper; role existence plus fresh explicit BEGIN READ ONLY readback reconciles the original exact issuance/OIDs, without replacing or resubmitting it. The verifier now uses the query endpoint with an explicit read-only database transaction. The temporary invoker adapter is removed. Actual Railway canaryda3c9776-95b9-4769-a9d8-562680bc0216 passes IPv6/CA/hostname TLS, SCRAM and required channel binding, owner/run/capability/raw-table denial and closed admission. Six actual default-bound transport reads including COMMIT/cleanup take0.230695–0.271458s. After original-pair revocation, both held sessions and fresh logins are denied. No new paper run/economic write/provider call.

Remove the six canary variables, retain only closed flags/public CA, restore /app/start-worker.sh and deliberately deploy ordinary closed worker9b6d169a-1298-4ba5-bbbb-a89483ce0b8a. Health200, unauth status401, foreign-Origin403 and docs404 all have no-store: HOST-05A passes. [Approved evidence](supabase/audits/2026-10-07-native-host-acceptance.json). Finite credentials/revoked bindings remain private/auditable; no broad DB/admin/deployment token enters runtime. Six samples establish connection feasibility, not long-tail, lease, relay, provider/quota or pilot readiness.

Next reviewed scope adds only vn_read to exact-project Data API configuration, preserving existing public/graphql schemas, search path, row/pool limits and grants. Private schemas stay unexposed. Original configuration is persisted before one patch, independently read back, and retained for additive rollback; anonymous/two-user and private-schema denial checks must follow. Existing exact-project publishable and legacy admin keys are valid; no key creation, rotation or shared login/configuration change is needed.


## 66. Curated Data API exposure and owned Auth/read canaries — 2026-10-07

PR59 source54b07547cbb598aa6aa59863797661477c3ef853 merges as817d3d3f8f39ed72d3363a90c8758ec40fe30a9d. Exact Vercel productiondpl_GbjkmQ8aksC2zcM9BrT4dxexbJYN is READY and four HTTP smokes pass. Fresh complete installed-body/grant verification and exact GitHub/Vercel/Supabase/Railway identity/closed/SSL checks precede one project-only Data API patch. Original configuration is privately retained. Only schema list changes from public,graphql_public to public,graphql_public,vn_read; search path/limits/pool/grants remain unchanged. Fresh configuration equality proves the intended result; rollback removes only that exposure.

Two explicitly owned temporary Auth users are created confirmed through the exact project's admin API, without sending email or changing an existing user's password. Their sessions remain private for finite acceptance. Both real Auth identities successfully call curated discovery and receive only their own identity with an empty directory. Anonymous discovery returns401/42501. For both users, vn_durability/vn_access/vn_release/dashboard_native_operator profiles return406/PGRST106: all remain unexposed. No paper run exists, so this does not prove nonempty cross-owner v5 history. The owner browser login remains a user setup step, followed by actual selected-worker/control/history acceptance. [Approved metadata](supabase/audits/2026-10-07-curated-api-acceptance.json).

Before configuring hosted Auth, repair the response memory bound: stream at most64KiB, reject duplicate JSON keys and invalid UTF-8 while retaining five-second total timeout, pinned host/no proxy/no redirects and secret-safe errors. Twenty-three Auth/paper-service tests pass, including oversize-stream early stop and malformed identity responses. Twenty-nine scoped operator tests pass. Auth-only closed startup and actual token/HTTPS canaries precede active worker/admission/provider/pilot work.


## 67. Actual hosted Auth and provider wire defect — 2026-10-07

PR60 source545808dfdb464e76d5b2c0dfaec42afb9d6c9abf merges as9b387967189ca9197b6a59beb2391835c78ff3c2. Exact Vercel productiondpl_ipmSqwHpMHdLk6uyf9jebXXZXByY is READY with four smokes. Explicit Auth-only service variables are read back exactly; no administrator/native/provider credential is added. Railway79327b5e-69fa-471e-9565-0a34d6739ccd serves the merged bounded Auth code, still closed. Real owned tokens reach503 Paper service is closed; missing/invalid tokens401, rejected Origin403, docs404, all no-store; exact-origin Auth preflight200. Existing owner signs in and saved legacy history is visible. Production still selects the legacy UI with an unavailable worker endpoint; selecting the reviewed paper UI/HTTPS endpoint is the next browser step. [Approved evidence](supabase/audits/2026-10-07-hosted-auth-acceptance.json).

Actual project-local Jupiter/Birdeye/Helius keys are present. Three SOL price/source captures pass at0.147911–0.397836s with source-age-at-receipt2.03–3.32s. Birdeye returns200 but actual unscaled candles include multiplier:null, rejected by the parser. The narrow repair retains None for absent/null metadata and preserves the explicit scaled-token guard. Original captured wire229,122bytes/SHA20610cf25c4a337c06720fc72cd3077f58c70fe3c8a1cdf4ae52d4abfc37566f now parses915 complete minutes/61bars; the extra forming boundary is validated and excluded. RPC responses are now bounded64KiB and reject duplicate keys/invalid UTF-8/nonstandard constants. No freshness, precision, coverage or execution policy is relaxed.

Explicit provider_read_canary runs only in closed mode with no native/admin/deployment credentials, serves closed HTTP during one finite assessment, and records actual adapter history/price/source timing, quota headers and CPU/RSS/loop lag. Twelve price samples with5s spacing,90s overall deadline and quota margin12 establish feasibility only; no retry, DB write, signing, swap, price-body or secret logging. Ordinary startup does not import the canary. Source is allowlisted into the non-root image. Validation:124 exact/source/feed/window tests,91 controller/contract/runner/service checks,5 canary ownership/quota/cancellation checks and9 scoped Railway/export tests pass. Hosted measurement remains pending until reviewed source is merged/deployed.

Current primary sources: [Jupiter organization-wide 60-second quota](https://developers.jup.ag/docs/portal/rate-limits), [Birdeye REST chart_type versus WebSocket chartBy](https://birdeye.so/data-api/changelog), [Helius current credits](https://www.helius.dev/docs/billing/credits). Current Helius billing lists getBlockTime at1credit; older/RPC-index documentation lists10. Budget against current billing and verify actual account meter before24/7 use. No plan upgrade/autoscaling/billing change. Local .env does not upload to cloud; the dedicated deployment token stays operator-only, and the public CA already reaches Railway as VN_DATABASE_CA_PEM.

User now requests deletion of pre-existing invalid bot records. Fresh original-scope private backup proves all five legacy arrays unchanged,15history versions and an empty closed v5 ledger; no external table references the legacy tables. Prepare a distinct bounded purge with fixed table/row-hash guards and rollback rehearsal. Preserve Auth/schema/history; never apply that purge to accepted v5 records.


## 68. Hosted provider feasibility, guarded invalid-data cleanup and closed browser selection — 2026-10-07

PR61 source3ace05e811a674586d733066e4985f9da751a2da merges asdf4da5a27054b7d81ea3584e520460e050e4158e. Exact Vercel productiondpl_HSWc5n61x88N17L8XNRdHX3i3xfC is READY with four smokes. Allowlisted merged export96files/1,195,246bytes/manifest457c179ebd06ddc68b90b034cdf14b44179d78191b13655e70d43ab265960c29 is deployed to the exact Railway provider-only canaryd6b8df39-9dee-41a5-b594-8db8f7b60421. Fresh API legacy region is null, but resolved serviceManifest.deploy.multiRegionConfig proves exactly one us-west2 replica; no region setting is changed.

Actual unscaled history915minutes/61bars accepts in1.201207s. One Jupiter/RPC capture accepts in0.183992s, source age5.742559s and receipt processing0.121394s. Process peak77,504,512bytes, CPU0.12s and maximum loop lag0.193406s are short feasibility facts. The probe stops with shared_quota_margin_unavailable because the returned remaining9 is below required12. It does not reach429 or retry, and makes no economic write. Do not reduce the margin or infer a plan from that one header. User clarification on existing Jupiter plan/shared organization allowance is pending; further current portal/header/quota research is needed. Restore ordinary start command, remove exactly the three provider variables, verify all original Auth/CA/closed variables unchanged and deploy56e0a351-ac64-4c24-a998-6bc8c7fc0eb4 successfully. [Approved metadata](supabase/audits/2026-10-07-hosted-provider-feasibility.json).

The user explicitly rejects all pre-existing bot data. Fresh private row snapshot matches the original five legacy arrays, totaling11,149rows; new v5 ledger has0runs/closedepoch0 and15migration versions. No outside FK depends on those five legacy tables. The fixed-table operation671260101efce09d83783f31511b564d6c8f7958edce93f5787714b41c00d379 locks the closed release and legacy writer tables, verifies exact counts and content hashes, deletes child-first without CASCADE, and requires all five empty before COMMIT. Actual identical transaction with finalROLLBACK passes2.132542s; fresh content hashes prove complete restoration. No schema/Auth/migration-history/grant changes. The private original backup remains diagnostic; it is not accepted research data.

The apply/reconcile operator requires exact four-provider identities/appliedSSL/closed worker, merged hash-pinned source and matching rehearsal/private backup, persists submitted_or_uncertain before one request, then proves fresh zero-row and complete installed-body/ACL/history/closed-release equality. An uncertain or remaining original does not authorize a repeated deletion. Six operator checks pass for original retention, content drift, partial outcomes, independent catalog verification and private file protection. Actual deletion follows merge; [reviewed operation](supabase/operations/2026-10-07-remove-invalid-legacy-bot-data.sql), [rollback metadata](supabase/audits/2026-10-07-invalid-legacy-data-review.json).

Production-only NEXT_PUBLIC_VN_SERVICE_MODE=paper-v5 and NEXT_PUBLIC_VN_API_URL=https://dashboard-paper-worker-production.up.railway.app are staged using the dedicated Vercel profile and exact project/team. Neither variable existed for production; no force/overwrite/shared/preview setting is used. They carry public configuration only; no worker key or native credential enters the browser. The next exact-source main build selects the closed paper interface. Actual owner curated directory and disabled controls must be verified in the already authenticated browser after that release and cleanup. This public selection does not open database admission or create a run.


## 69. Invalid legacy cleanup committed and closed paper browser verified — 2026-10-07

[PR62](https://github.com/TOOTRJ/TheDashboard/pull/62), source `b1debdd5604198dcceac55514f1de2b9df275419`, merges as `b814cb0deb11a90aa0a6133a74451790049fe1b6`. Exact Vercel production `dpl_6BgKm2V4o63P2aXv5RNXvDszaV2x` reaches READY; project/team/repository/author/source and production alias match, and all four read-only smokes pass. The production-only public paper settings now select the v5 browser interface and the exact Railway HTTPS origin.

The exact four-provider target checks and applied SSL/closed credential-free worker guard pass before the one deletion submission. Source hash and origin/main bytes match the reviewed operation, original rows match the private snapshot, and the prior identical rollback rehearsal is required. The operation commits; independent fresh reads prove all five legacy tables empty. Deleted counts: 8 colonies, 497 probes, 807 trades, 9,837 fitness snapshots and zero generation summaries: **11,149 old bot rows**. Full installed body/ACL/catalog/history verification passes, fifteen migration versions remain, and v5 admission stays closed at epoch0 with zero runs. Schema, Auth, grants and migration history are not modified. The private ignored original backup remains diagnostic recovery evidence; rejected data must never enter accepted v5 research. [Approved acceptance](supabase/audits/2026-10-07-invalid-legacy-data-acceptance.json).

The existing signed-in owner at the production /probes page sees Evolutionary paper pilot, an empty new run selector, Legacy history (0 runs), and disabled start/stop/settle. There is no history-read error. The warning that the worker cannot yet be verified is expected from deliberately closed startup; it is not active-flow acceptance. Railway remains on ordinary Auth-only closed deployment `56e0a351-ac64-4c24-a998-6bc8c7fc0eb4`; temporary provider and native credentials are absent. No paper run or live transaction is created.

Browser inspection also finds unsupported surrounding Live, Connected and All Systems Operational claims attached to demo prices/static badges. UI-05A relabels the header/sidebar prices as demo and removes the unmeasured global service claims. The paper panel's actual guarded worker status remains authoritative. Focused typecheck/lint and exact release/browser verification accompany this small correction.

Immediate dependencies are actual Jupiter plan/shared quota availability, completion of finite source timing and remote lease/SQL/relay/CPU measurements, then hosted nonempty ownership/operator/interruption/overlap acceptance before one bounded paper pilot. Deep substantial research on quota billing, remote tails, retained exposure, restart semantics and longer-window checkpoints remains in TODO.


## 70. Jupiter upgrade, current contracts and finite quota-guard repair (2026-10-07)

Read-only signed-in portal inspection confirms an active monthly Developer plan and the existing Dashboard key matching local configuration. A deliberately bounded actual Price V3 read is attributed to that key, charged1credit and allowed without a matching firewall rule. Local adapter elapsed0.297689s/source age4.924889s uses one Jupiter/two RPC/no Birdeye calls. Numeric response headers current1/remaining9/reset about10s still do not prove the documented Developer600requests/60s organization quota. Billing, keys, firewall and other projects remain unchanged. Effective capacity/shared-use acceptance stays open as DATA-01E.

The complete current documentation index and actual versioned Price V3/Tokens V2/Swap V2 OpenAPI files were retrieved; [review manifest](services/vonneumann/jupiter-api-review-20261007.json) pins URLs/bytes/SHA-256. The old unversioned Swap skill link is V1, not the current contract. Source already uses Price V3 and quote-only Swap V2 with exact atomic inputs and percentage-point impact conversion. Price createdAt is mint creation; wallet total-flow fields belong to execute. No deprecated Jupiter runtime host/V1/Ultra call was found.

The older provider canary incorrectly required all twelve future requests to fit the current remaining allowance despite5s pacing, and treated an absent remaining header as adequate. The reviewed repair requires a recent explicit numeric remaining count of at least3 for each subsequent request: one call plus two observed reserved slots. Missing/stale/low evidence refuses; no retry, reset-based full-window assumption or continuous account-budget acceptance is introduced. Sample/deadline/resource bounds and closed HTTP/no database credential/no wallet operation remain unchanged. This supersedes section68's instruction against an unexplained margin reduction: the change corrects a proven burst-model defect and does not lower active controller policy.

Focused offline acceptance passes57 provider/feed/canary tests and106 disjoint quote/freshness/candle/evidence/record tests. The seven canary cases include low/missing/stale evidence, paced remaining9 success, configuration denial, failure and cancellation resource cleanup. No live fill or SQL mutation is exercised. Before the actual revised assessment, verify all four exact targets, use only merged immutable source, save private original variables, add only the three provider values temporarily, and restore ordinary Auth-only closed startup/variable equality after the finite result. Reconcile the original deployment on uncertainty; do not repeat a submission blindly.

[Updated research](services/vonneumann/JUPITER-DATA-RESEARCH.md) recommends retaining Birdeye narrowly for the implemented two-EMA profile's61 completed15-minute warmup bars and completed candles. Jupiter supplies current prices/quotes but no documented general historical range. Deeper RES-03 work can validate durable sampled reference closes later. Portal diagnostics and Tokens screening are useful; managed swaps, beta fast build, transaction V1 and Trigger protective orders belong to later measured/custody-reviewed live work. AMM/RFQ tools do not serve this ordinary paper bot. Existing project skills/read-only documentation configuration suffice; no global tools, wallet/trading MCP or other agent configuration were changed.


## 71. Actual revised hosted provider acceptance and restored closed release (2026-10-07)

PR64 merge02c0e2d54b8d3d0d85848b1bc1f264899d26719d has exact Vercel productiondpl_H2Gh2Tnbi2KKs7Qo72CqQ5HVETGc READY on the authorized project/team/repository/author; production alias and all four read-only login/redirect/zero-row API smokes pass. Exact four-provider target/owner/service/environment and SSL checks precede the deliberate Railway assessment. Source export includes 96 allowlisted worker files and no credential/environment/SSL file.

Provider-only closed deployment1697fedb-a752-49e8-ad19-dd454fe2fc89 passes915 completed minutes / 61 warmup bars in1.138719s and all 12 paced price captures. Complete price/RPC validation minimum0.113060 s / median 0.116141 s / maximum 0.195100 s; source age3.225096–5.486115s; receipt processing0.075190–0.125034s. Twelve Jupiter/one Birdeye/thirteen RPC calls, elapsed57.654938s, peakRSS75,558,912bytes, CPU0.25s and maxlooplag0.228707s are finite facts, not p95/p99/sustained capacity. No retry/economic write/wallet operation. Quota first current=1 / remaining=9, then current=2 / remaining=98 demonstrates increased observed headroom but leaves window/shared-use acceptance DATA-01E open. Do not infer that these reset headers prove600requests/60s.

Restore ordinary `/app/start-worker.sh` and remove exactly JUPITER_API_KEY / BIRDEYE_API_KEY / VN_SOLANA_RPC_URL. The entire original variable set matches private saved originals; no native/admin/operator credential is present. Ordinary closed deployment9f606944-1bfd-4b2c-87bc-0855bee00117 SUCCESS uses the same immutable source and authoritative one us-west2 replica. Fresh exact-target/SSL/service/limit checks, health 200, anonymous status 401, disallowed origin 403 and no-store pass. [Sanitized evidence](supabase/audits/2026-10-07-upgraded-hosted-provider-acceptance.json) retains measurement and restoration. Private source/upload/original-variable journal remains mode 0600, ignored, and settled as passed_and_restored_closed. No migration, Auth/legacy data change, account-wide rule/billing change or live/paper run.

DATA-01D now completes its finite compatibility/measurement scope. Immediate remaining work is D2D2A remote source/SQL/lease/relay preparation/resource headroom and DATA-01E shared quota/credit budget, followed by safe interruption/nonempty ownership/operator acceptance and HOST-07. Birdeye stays narrowly for completed historical warmup/candles; the two EMA genes stay fixed until that pilot is accepted.


## 72. Remaining paper MVP admission repairs and finite controller assessment (2026-10-07)

The user confirms no other application consumes Jupiter under TheOrder. The
Dashboard remains the only authorized cloud target. Fresh GitHub, Vercel,
Supabase and Railway project/name/owner/service context is pinned;
Railway is still ordinary Auth-only closed deployment9f606944-1bfd-4b2c-87bc-0855bee00117,
one us-west2 replica, .25CPU/500MB and no native/provider runtime credentials.

Review found three defects: configured lease duration did not establish actual
remaining wait headroom; successful journal reconciliation/publication could
return without a renewed lease; and a strict 3,600-second pilot cutoff could
reject the first paced quote that completes a 3,600-second evaluation. Repairs
use conservative acknowledged remaining time and a bounded idle renewal, renew
after readback/publication before normal admission, and allow sixty seconds
for first-window completion while stopping at the existing one-replacement
latch. All command/payload/retention caps and the fixed v5 horizon stay intact.
A fourth operational issue prevented scoped credential revocation after release
activation; the private temporary invoker now permits exact-pair revocation
also while open/retired, while issuance remains closed-only. Isolated actual
PostgreSQL activation/retirement/revocation rollback drills pass. No managed
release activation or new credential issuance has occurred at this checkpoint.

The deliberate finite controller canary composes ordinary configured service,
real feed/native SQL/durable relay and reserved stop with at most thirty ticks,
five-second minimum spacing and600s deadline. Its secret-free measurement
wrapper retains counts/timings only and does not retry. Public API remains closed.
Its actual hosted acceptance, interruption/nonempty ownership and supervised
one-window pilot remain the next gates; do not mark them complete from tests.
Deep substantial research remains for statistical remote tails, provider credit
entitlements, restart/retention and multi-window checkpoints.

Validation: the full ordinary worker discovery runs1,713 tests in254.291s, with237
opt-in PostgreSQL cases skipped. Four separately added canary boundary tests pass;
the selected actual PostgreSQL run passes13 cases including open/retired exact-pair
revocation, controller ownership and the native HTTP/projection/relay flow. The
focused worker regression run passes192 cases and the focused new tool/service/
runner/package run passes47. Scoped operator scripts pass29 tests. No frontend
source changed; diff/whitespace checks pass. The pre-existing dirty historical
migration remains untouched at SHA256a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc.

Current remote blocker2026-10-08: fresh GitHub/Supabase/Railway identity checks
pass, but dedicated Vercel CLI62.0.0 reports a native credential error (positive
errno1); the Node path cannot resolve the dedicated session either. The dedicated
auth.json is unavailable on fresh inspection. No default/shared credential or
profile is used. Require deliberate login to the exact Dashboard profile before
consequential push/deployment/activation. [Reviewed activation/rollback plan](PAPER-MVP-ACTIVATION.md)
records original-ID gates and one-way release retirement. No remote write, new
pair, release activation, or paper run occurred in this repair checkpoint.

Follow-up regression: lost first-replacement replies settle the committed original
and publication without trying normal readmission through the completed-pilot
latch; the reserved stop performs its own renewal. The literal provider/adapters
and real sealed candidates exercise a full hour with five accepted quotes and
immutable overlapping candles; no replacement/price is repeated. Focused
controller/runner/service/canary checks pass76 tests, and production inventory/
cadence guard checks pass12. Production selection explicitly requires the sole
consumer acknowledgement and interval>=5 before native construction. The user
has completed the deliberate scoped login; fresh remote target verification is
being repeated before any push or activation.

## 73. First hosted controller measurement and consumed-history repair (2026-10-08)

The dedicated login now resolves the exact Vercel project/team. PR66 merges as
816f3006ba0930ebb531ce1a567984033aab293c; productiondpl_8oikhTvcKt4qVrug3WyHxJ8PsRHy
is READY with matching project/team/repository/author/source/alias and four
read-only smokes. Full Supabase body/authority verification and fifteen migration
versions match. Four finite owner/run economic/relay pairs are issued through
bound private inputs while closed; the temporary invoker is removed. The original
release transition is rehearsed under ROLLBACK, then committed once and freshly
reconciled: open, epoch1, unchanged catalog/release digest. No schema migration
or live transaction occurs.

Railway controller assessment394e3780-c769-4c59-a3ca-d346df9c4b5b uses the merged
97-file credential-free export, one us-west2 replica and closed public controls.
It commits create/bootstrap and publishes/acknowledges nine original events,
then refuses before any price request. The startup history receipt was kept as
an admission guard throughout cumulative relay publication and expired despite
already committed installation. Elapsed8.390702s, peakRSS99,815,424bytes; bootstrap
SQL0.655003s; nine accept calls0.240691–0.263967s and nine ACKs0.243925–0.253273s.
One Birdeye call, zero Jupiter/RPC captures; no SQL errors. This is evidence of
the blocker, not accepted source/lease/paper operation.

Ordinary closed deployment00f46f23-77f6-49ef-9518-63a0546f18ad is SUCCESS on the
same exact service/source/region. All sixteen assessment-only variables are
removed; the whole saved original variable set matches, including the preexisting
CA. Original committed history is preserved. Finite database pairs remain scoped
in their private journal for explicit drills/expiry/revocation; runtime removal
is not a claim that their database logins have already been revoked.

The repair consumes history freshness only after exact candidate installation.
It preserves pre-acknowledgement history expiry and all price-ticket guards.
An explicit lost-reply drill discards one acknowledged bootstrap response and
reads the same retained command, without resubmission. A distinct existing-run
drill checks new-worker command conflict and expired heartbeat on actual native
SQL, commits one original interruption ID/revision, and retains checkpoint and
holdings. Both keep public API closed. Hosted rerun, nonempty owner isolation,
deployment faults and the one-hour pilot remain pending; larger remote tails,
provider credit costs and continuous/restart operation remain deeper research.
