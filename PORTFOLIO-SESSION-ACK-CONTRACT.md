# Portfolio account/session publication and write acknowledgments

Status: reviewed local implementation, 2026-10-13. Base is
`c04be4fb536c593541603a7e7c6c1140771b139d`; the isolated branch is
`codex/dashboard-portfolio-session-ack`. This slice changes the Portfolio page
and its data helpers, adds controlled component/helper tests, and implements no
authentication policy, schema, financial formula, wallet, provider, deployment or
cloud-account change. Root owns integration and release acceptance.

The old page retained private goal/editor/add fields on logout and left mutation
callbacks able to publish after an account or login changed. Goal Undo ignored a
failed update and reported success. Delete and goal update treated an error-free
response as acknowledgment even when no owned row was affected.

## Implemented behavior

The page derives an internal lifecycle identity from the current login using the
existing `sessionIdentity` helper. An opaque random React key owns a separate
Portfolio workspace per account/login; bearer tokens never appear in React keys
or rendered copy. Loading and signed-out/mismatched-session boundaries hide
private workspace content immediately. Ordinary token refresh within the same
Supabase `session_id` preserves the workspace. Re-login, account replacement,
unmount and Strict Mode effect reestablishment invalidate captured requests.
The existing authentication and scoped-client implementations are unchanged.

Every read and add/edit/delete/goal/Undo write captures the existing workspace
scope. The existing scoped data client verifies the actual current owner/login
and binds its data requests to that login's original token, without persisted
Auth state or an automatic token-refresh client. Owner predicates and server RLS
remain required. A late reply cannot set private state, clear a new pending
operation or issue a toast in a replacement workspace.

One mutation at a time owns this workspace, including double clicks before a
pending-state repaint. Inputs and competing controls are disabled while it is
pending. A request object owns cleanup: an old Strict Mode request's `finally`
cannot unlock or clear a newer operation. This is browser publication/order
protection, not a server compare-and-swap, cross-device serialization or proof
that an already dispatched server write was cancelled.

Add/edit validate the returned owned account row; edit also verifies the exact
requested ID. Delete uses both requested ID and captured owner predicates and
requires one returned row with those exact identities. Goal update requires one
returned profile row with the captured owner and the exact requested saved
amount/year. Empty/foreign/wrong-ID/provider-error replies cannot produce a
successful change. No automatic retry is added.

Returned account balances and goal amounts must be genuine finite nonnegative
numbers or nonempty decimal numeric strings; year must be null or a genuine
safe integer number/numeric string. Boolean, object, empty-string, hexadecimal,
nonfinite and fractional-year aliases are refused. Account rows retain their
actual nonempty supplied `updated_at` string; no timestamp is fabricated.
Account list shape and present goal object shape are checked. Malformed scoped
reads and actual read errors show unavailable/retry state, rather than invented
zero/empty success. The preexisting documented missing-profile default remains
zero goal/null year; that default is not a successful write acknowledgment.
Money remains the existing Number representation; exact financial accounting,
calendar/range policy and financial-model calibration are outside this slice.

Every Portfolio notification has a supplied opaque owned ID. The workspace
retains at most eight IDs, removes them on individual dismiss/auto-close, and
dismisses only those IDs at layout cleanup. Success notices never include account names, balances, goal values or other
private descriptions; those values stay inside the keyed private view. The
installed Sonner implementation schedules dismiss through animation frames and
a 200-ms exit animation, so owned-ID cleanup is logical API retirement, not
proof of synchronous DOM removal. Keeping notice text generic removes private
content from that global-animation seam. Cleanup leaves unrelated Sonner
notifications intact. An old auto-close callback
cannot remove a new notification's distinct ID. No global toast dismissal is used.

Undo belongs to the original acknowledged goal action and workspace. A goal
edit or later goal save invalidates that action. Retired Undo cannot dispatch a
write; a live Undo awaits its own exact acknowledgment. Failure preserves the
acknowledged goal/draft and reports inability to revert. Only successful current
acknowledgment restores the original goal and reports it reverted.

## Local evidence and limits

The final credential-empty Node 24.19.0 controlled run:

```text
node --test tests/portfolio-session.test.mjs tests/portfolio-ack.test.mjs tests/nestegg-storage.test.mjs
```

passed **51 tests in 720.072166 ms, zero skips**: 18 page lifecycle/action cases,
21 new helper/acknowledgment cases, and 12 existing Nestegg storage/scoped-client
regressions. The page harness executes the actual TSX and callbacks with
controlled hooks/JSX, deferred replies and effect cleanup/setup. The helper tests
execute the actual Portfolio helpers plus the existing scoped-client code with
fake authenticated identities and query replies. They test retirement after
submission, not just before identity lookup. These are not React DOM, native
keyboard/portal, real two-user browser, Supabase/RLS or live database acceptance.
All fixtures use public fake identities and no provider/backend requests.
Five added cases specifically check already-visible generic owned notifications across
account/logout/new-login/Strict Mode changes, unrelated-notification preservation,
old Undo retirement, auto-close and the eight-ID bound. Successful private account names are never published to the global toast API. This is controlled API
publication evidence, not a claim of actual Sonner DOM removal timing.

Before the owned-toast follow-up, TypeScript and scoped ESLint passed with zero
errors or warnings. A fresh allowlisted isolated production build using the existing `check-build.mjs`,
literal fake application configuration, owned empty user/global npm files and
pinned Node compiled all 18 routes; **153 frontend files / 1,360,390 bytes** were
copied. That build is historical pre-toast evidence, not final-toast-source
acceptance. A final source-bound build follows when the coordinated slot is free.
The owned copy was removed by the helper's successful finalizer. Existing
ESLint deprecation/no-build-cache notices are not runtime failures. No `.env`,
SSL folder, shared authentication/configuration or production data was copied.
The initial missing npm PATH attempt refused before the build, and a prior build
snapshot is not the later response-shape or toast cleanup evidence.

The earlier broad 303-case frontend run had 302 passes and one existing
missing-profile semantics regression introduced during this repair. That
regression was corrected without changing the existing test, and the final
51-case run above exercises it. It is not relabeled as a complete current-head
303-case pass. Root's integrated complete CI and actual authorized browser
acceptance remain separate release gates. No Dashboard cloud target was contacted or modified by these mocked tests or
production compilation. The isolated locked npm installation fetched public
dependencies into its owned build directory.

## Final generic-notice source build

After root and source peer review, private success descriptions were removed
from all three account actions; exact-owned-ID cleanup and retired Undo guards
remain. The final 51-case receipt above tests these precise source bytes.
TypeScript and scoped no-cache ESLint pass with zero errors/warnings. The fresh
allowlisted Node 24.19.0 fake-configuration production build passed all 18 routes
from **153 files / 1,360,976 bytes**, using its own locked install, literal fake
application configuration and owned npm paths. The helper completed exact marked
copy removal; no server/worker was started. No package, credential, cloud or
shared configuration changed. Root's integrated CI/actual authorized browser
acceptance remains a separate release gate.

Final implementation/test source pins:

| File | SHA-256 |
|---|---|
| `src/app/(dashboard)/portfolio/page.tsx` | `e46470132a7eba2a84318ab25c8266203c9d88ea56333311406445e2b076a0ff` |
| `src/lib/portfolio/portfolio-supabase.ts` | `486da0ed8a57d9200f0300ddf13bec2b5b5fe3a8cfd2b2ff97427535908ccc3e` |
| `tests/portfolio-session.test.mjs` | `47b5fd5c47572587d0c8d9062e2197daf9311d56986ff57c239fe3c59483c5ba` |
| `tests/portfolio-ack.test.mjs` | `0038d40d1486ae39362ec560f8abffd533e91fa0af260fe6b78710b96cef8f9e` |
| `tests/helpers/portfolio-harness.mjs` | `d4bdfd8d07953415b8fc0444ddae3485f0426cf63be58ae91ac70c5ed25af8e0` |

These hashes bind the local bytes and test scope; they do not attest a cloud
deployment, provider, financial model or server authorization. The contract's
own Git-reviewed bytes are separate from this table to avoid a self-hash cycle.
