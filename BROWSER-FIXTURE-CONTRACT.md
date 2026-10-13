# QA-01B: isolated real-browser fixture

This development harness runs the actual Next.js/React frontend and its Auth,
saved-plan and paper-dashboard components against synthetic services. It is not
a deployment, a Supabase emulator, an authenticated production acceptance test,
or permission to start a trading worker.

Run `node scripts/browser-fixture.mjs` using the pinned project Node runtime.
The launcher accepts no arguments. It copies only tracked frontend inputs into
a fresh ownership-marked temporary directory, installs the locked dependencies
there, builds with fake credentials, and starts its own loopback servers. It
does not copy environment files, certificates, cloud configuration or existing
build directories. A unique `dashboard-fixture-<uuid>.localhost` app hostname
isolates browser cookies from other local projects. The fixture-only CSP admits
only the app and its owned backend; production configuration is not edited.

The synthetic accounts are `alice@dashboard.invalid` and
`bob@dashboard.invalid`, with password `fixture-password`. Their data and tokens
have no cloud authority. The backend rejects other accounts, owner mismatches,
unknown APIs, foreign browser origins and oversized bodies. Its fake admin key
permits only a zero-row GET of `test_events` for the frontend API smoke test.
Logout retires the logical session, including its refresh tokens. A held reply
retains the original response so account-switch races can be exercised through
the real UI, rather than changing the response to fit the new account.

The `/paper-fixture` route exists only in the temporary copy. It renders the
actual `PaperDashboard` with explicit synthetic API adapters. Its controls can
hold/reject/release original replies, lose Start/Stop acknowledgments, return
unknown contracts or oversized reads, and close the synthetic worker. It makes
no actual RPC, worker, wallet or provider calls. Literal retained assessment
fixtures are public test material; passing them is not evidence of profitability
or a working hosted provider integration.

The ready record supplies exact owned process IDs, origins and directory marker.
Stop the launcher with SIGTERM or SIGINT. It waits for its exact child process
groups to disappear, including descendants whose parent has already exited,
before removing its own temporary directory. It never enumerates or terminates
another project's processes. The tests exercise both surviving-parent and
surviving-descendant cleanup. No global Docker, CLI or credential changes are
part of this harness.

Acceptance must record the exact application commit, observed UI outcomes,
actual held-request barriers, refusals, console errors and cleanup. Adapter and
hook tests do not substitute for the real browser observations. Hosted CI and
production acceptance remain separate gates.
