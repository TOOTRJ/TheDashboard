# Nestegg account and login-session isolation

NEST-06A, implemented 2026-10-12. This repairs browser draft ownership and
asynchronous account/session publication. Financial formulas, return
distributions, optimizer behavior and same-account input/model calibration are
unchanged.

## Device drafts

The former origin-wide `nestegg-draft-v1` is deliberately preserved but never
read, imported or assigned to the next signed-in account. New drafts use an
owner-tagged v2 envelope at `nestegg-draft-v2:<owner UUID>`. Reads reject another
owner, malformed envelopes and oversized input. Blocked storage and quota
errors become explicit unavailable states rather than crashing hydration.
Clearing affects only the requested owner's draft.

Signed-out state mounts no financial workspace. This namespace prevents normal
application account switching from showing another owner's draft. It does not
encrypt local storage or protect against a person inspecting the same browser
profile; account authentication is not an OS/browser-profile security boundary.

## Workspace and asynchronous ownership

The page creates an opaque workspace key/scope per authenticated account and
login identity. Neither raw bearer tokens nor internal session identities appear
in React keys or direct workspace props. Supabase's stable `session_id` preserves
the workspace during normal token refresh. Opaque or legacy tokens without that
claim use internal exact-token comparison; a changed token conservatively
creates a new workspace.

Captured scope revisions retire hydration, refresh, autosave, scenario operation,
portfolio read, Monte Carlo/progress, export state and delayed focus callbacks on
account replacement, logout, re-login or Strict Mode effect replacement. The
keyed workspace removes private views before the next account's render rather
than waiting for an effect to clear old inputs.

Each scenario request validates the current server user and current login
session before creating its own Supabase data client. The client snapshots that
verified token through the SDK's `accessToken` callback; it does not borrow a
replacement shared Auth session or persist/refresh its own Auth state. Owner
predicates and server RLS remain in force. Returned foreign-owner rows are
refused. Portfolio reads can accept the same scope while preserving the existing
Portfolio page's optional-scope interface.

Already-dispatched operations may finish under their original authority. Their
retired replies, toasts and callbacks are discarded. Logout does not undo a
committed write, and the client does not report an uncertain write as reversed.
Current query/auth failures are distinguished from successful empty plans so
device defaults are not silently substituted for an unavailable cloud read.

## Verification and remaining scope

Twenty-one focused Node cases execute the actual implementation through the
existing VM/hook test approach: A/B switching with no plans, wrong-owner drafts
and rows, blocked storage, delayed Auth replacement before dispatch, token-bound
requests, late reads/saves, cancelled autosave, old Monte Carlo result/progress,
logout and same-owner re-login, Strict Mode retirement, ordinary token refresh,
and opaque key/direct-prop serialization.

The complete privacy snapshot passes **204 Node tests**, TypeScript, broad
source/test lint with zero errors and32 existing warnings, and an isolated
fake-configuration production build. Dependencies are the reviewed security
lock, without modifying another project's tools or configuration. No real
browser/React/Auth/TLS two-user acceptance or financial-model certification is
claimed; that remains QA-01B and the broader Nestegg gates.

NEST-05A still requires input/model/seed identities for same-account light/full
results and exports. NEST-01…05 calculations/calibration, broader portfolio-link
semantics and export behavior remain open. No migration, hosted test data,
credential or financial operation is needed for this repair. Rollback is a
reviewed code/docs revert; reverting would reintroduce the old draft/session
privacy behavior and must not be treated as a safe storage migration.
