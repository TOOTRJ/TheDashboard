# Dashboard native credential operations

The closed migration is installed on The Dashboard only. Run the project-only
`scripts/dashboard-native-credentials.py` from the exact repository. This is an
operator action; the application never imports the issuer or a management token.

The existing Supabase CLI Keychain profile is read into process memory. No login,
logout, shared credential/configuration write, token output, proxy or redirect is
used. The helper permits only exact-project identity and database-query paths.
Both immutable project/name/owner verification and the existing full GitHub,
dedicated Vercel, Supabase SSL/link and closed Railway checks precede operations.

The Management API currently accepts bound parameters for one statement, while
bound multi-statements fail. Actual managed DDL logging cannot be disabled by the
limited installer. The temporary `dashboard_native_operator` schema contains two
postgres-owned SECURITY INVOKER functions with no PUBLIC/API/capability grants.
They grant no authority to their caller. The body requires the measured limited
postgres profile, exact closed release, safe logging settings, validated finite
scope/verifiers, and the original reviewed role/binding postconditions. Nested
error details are discarded. The top-level SELECT contains parameters, not
literal verifier/password material. The adapter is removed with RESTRICT;
unexpected objects prevent removal rather than being deleted by CASCADE.

`prepare` persists one fresh pair/run scope before any credential request in
owned mode0600 `ssl/maintenance-20261007/native-canary-original.json`. `issue`
requires that original prepared state and the reviewed adapter in origin/main.
Two independent 256-bit secrets produce SCRAM verifiers; inputs are bound, never
placed in SQL files, command arguments, Git, reports or worker images. The pair
is owner/run/capability bound, has connection limit2, no inherited/admin/SET
authority beyond its one capability, a finite write deadline and bounded
recovery LOGIN deadline. No run, funding, signing or provider call is created.

`reconcile` reads only the original issuance IDs and verifies exact names, OIDs,
owner, run, capabilities, restricted role attributes and password/binding deadline
agreement. An absent/mismatched outcome is a failure, not permission to create a
replacement. `revoke` uses retained original scope/OIDs without old passwords,
sets revoked_at and NOLOGIN atomically and preserves immutable bindings/history.
Adapter-install/cleanup uncertainty requires explicit original-object review.

The explicit `tools/native_session_canary.py` operator command runs only with
closed mode and a finite pair. It verifies the fixed IPv6 endpoint, reviewed CA,
hostname/TLS, required SCRAM/channel binding, actual default transport samples,
owner/run/capability/raw-table denials and closed release refusal. It holds the
original two sessions for up to45 seconds while the operator revokes that pair,
then verifies held-session and fresh-login denial. It never starts a paper run,
retries an economic operation or becomes normal worker startup. On success it
executes the ordinary closed worker; restore its ordinary start command and
remove canary service secrets afterward. Logs contain only approved booleans,
phase names and finite sample timings. These few samples do not prove tail
latency, provider/relay/lease reliability or paper-pilot readiness.

Research remains for managed-hook changes, native dependency/CA expiration and
credential lifetime/rotation, safe parameters/logging under changed policies,
actual connection/COMMIT tails, shared provider quotas and interruption exposure.
Current API documentation: https://supabase.com/docs/reference/api/v1-run-a-query.

## Fresh pair after terminal cleanup

The separate opt-in issue_quiescent adapter requires the exact OPEN release,
all old bindings revoked/NOLOGIN, no other application capability LOGIN, no
active/unreconciled run and a previously unused run/binding identity. Independently
prove the exact Railway worker is closed and credential-free before installing
it. The trusted postgres issuer exclusion still requires the existing limited
issuer/logging boundary. Default closed issue/install/remove bytes are unchanged.

rehearse_quiescent accepts the same single bound JSON input. Its nested exception
subtransaction invokes the real issuer then rolls every database change back;
only a local receipt survives. Issuer errors become a fixed failure, never a
successful rehearsal. Independently read role/binding absence before one actual
issuance, reconcile original immutable scope/deadlines and remove both temporary
functions/schema with RESTRICT. No password/verifier enters function DDL or logs.
An unknown issuance outcome requires original-ID readback, not a new pair.
