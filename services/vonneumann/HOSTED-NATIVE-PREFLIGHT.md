# Hosted native connection and credential preflight

DB-03A2D3B2C3A, reviewed 2026-10-06. This completes the read-only metadata and
TLS-only operator tooling slice. **C3 stays open:** project CA provenance,
worker-host reachability and actual scoped native authentication are unproved.
No provisioning runner, production SQL, credential, server configuration or
startup selection is introduced. The worker remains unhosted.

## Actual evidence and its limits

Fresh dedicated GitHub/Vercel metadata and Supabase project metadata match only
TOOTRJ/TheDashboard / 1141090963, the-dashboard / prj_wFUe9k9USVreOQcmQKNWRAVsx5fH /
team_8iNNxiNjrOseD4gdSCHkQEzF, and The Dashboard / fxpxsciltakyypunglzr /
cqfnnaunmupdyobkyqfo. Local links match. The read-only capture is in
[the approved metadata JSON](../../supabase/audits/2026-10-06-vonneumann-native-profile.json)
and [the bounded SQL](../../supabase/audits/vonneumann-native-profile.sql).
The query uses repeatable read/read only, 15-second statement and 1-second lock
timeouts, then ROLLBACK. No application rows, passwords, role password hashes,
function bodies or unrestricted settings are retrieved.

| Fact | Observation | What it establishes |
|---|---|---|
| Engine | PostgreSQL 17.6 | Fits the candidate's major-version requirement. |
| Server TLS capability | `ssl=on`, minimum TLS 1.2 | Server can negotiate TLS; does not require it for every client. |
| Project SSL enforcement | `currentConfig.database=false`, `appliedSuccessfully=true` | Non-SSL database connections are not rejected by this project setting. |
| Management query session | TCP, `session_user=postgres`, `system_user=scram-sha-256:postgres`, TLS 1.3/256-bit cipher | This management backend uses TLS/SCRAM. It is not the worker's direct session, CA/hostname verification or SCRAM channel-binding proof. |
| Password-encryption default | `scram-sha-256` | Default for newly set passwords, not evidence about every existing role password. |
| Connection ceiling | 60 total, 3 superuser reserved, 0 other reserved | Configuration ceiling; not available worker capacity. Existing services and managed overhead consume slots. |
| New schema/roles | `vn_durability`, `vn_read`, private owner, economic and relay roles absent; native role count 0 | No C1/C2 runtime identity or schema is deployed. |
| Migration ledger | Same fourteen versions through `20260930030000` | This read introduced no migration. |
| Direct DNS | 0 public A records, 1 public AAAA record | Current direct endpoint is IPv6 only. |
| Local macOS network | System `getaddrinfo` failed; explicit DNS AAAA lookup succeeded; TCP to that IPv6 address reported network unavailable | Local native acceptance cannot run on this connection. No authentication/TLS attempt occurred. This is not a hosted-worker test. |

The experimental SSL GET is an identity-pinned metadata read. Updating the setting
restarts the database; do not toggle it as part of this preflight. Before any later
change, inventory this Dashboard's database clients, verify they require TLS,
prepare a maintenance/recovery plan, and approve the reviewed action. HTTP APIs
already enforce HTTPS. Client `verify-full` remains mandatory regardless of the
server toggle. [Supabase SSL enforcement](https://supabase.com/docs/guides/platform/ssl-enforcement),
[GET response contract](https://supabase.com/docs/reference/api/v1-get-ssl-enforcement-config).
The current off setting does not pass the intended server-side TLS-only gate for
credential provisioning. Keep issuance closed until a reviewed Dashboard client
inventory and maintenance action establish that gate; the management session's
encrypted connection is not a substitute.

## Certificate acquisition and safe network test

1. Open the exact project
   [Database Settings](https://supabase.com/dashboard/project/fxpxsciltakyypunglzr/database/settings).
   Confirm **The Dashboard** and the project reference, then download its SSL CA.
   Keep the password and SSL toggle unchanged. The in-app browser is signed out;
   manual download is the current missing input.
2. Keep the public CA in a project-private ignored location or approved worker
   secret-file store; never append it to shared `~/.postgres/root.crt`. Record
   download source/time, exact PEM SHA-256, each DER SHA-256 and validity range.
   A copied filename, parseable CA or matching local hash alone does not prove
   project provenance. Supabase documents downloading the CA from this settings
   page for client verification. [Connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres).
3. Run the explicit inspection tool with the existing isolated hash-installed
   worker Python; no network is used without `--probe`:

   ```sh
   /absolute/isolated/venv/bin/python tools/native_tls_preflight.py --ca /absolute/reviewed/public-ca.crt
   ```

4. After provenance/hash review, run from the **selected worker environment**:

   ```sh
   /absolute/isolated/venv/bin/python tools/native_tls_preflight.py \
     --ca /absolute/reviewed/public-ca.crt --probe \
     --expected-sha256 REVIEWED_64_CHARACTER_LOWERCASE_PEM_SHA256
   ```

The tool pins only `db.fxpxsciltakyypunglzr.supabase.co:5432`. It sends PostgreSQL's
eight-byte SSLRequest, requires the `S` reply, verifies the hostname/chain using
only supplied CA roots and TLS >=1.2, captures bounded certificate metadata, then
closes. It sends **no StartupMessage, login, password or SQL**. Its return labels
authentication/channel binding as untested. There is one public DNS address
attempt, no pooler/private address/profile retry and no environment/default trust
lookup. A seven-second socket deadline runs inside one isolated child with a
ten-second parent timeout; an OS DNS stall cannot retain an unbounded probe.
Only that owned child is killed/reaped on timeout. Diagnostics are fixed codes.
The current local IPv6 failure is a reason to test the selected host, not to relax
certificate verification. [PostgreSQL SSL negotiation](https://www.postgresql.org/docs/17/protocol-flow.html),
[Python subprocess timeout ownership](https://docs.python.org/3.12/library/subprocess.html#subprocess.run).

The CA inspector caps input at 64 KiB and accepts only distinct current CA PEM
certificates, with certificate-signing usage when present. It rejects leaves,
private keys, trailing non-certificate material, duplicate/expired/future roots.
It reports hashes/expiry without certificate subjects or paths. This does not
provide revocation checking or infer that every parseable root is authorized.
The actual C2 libpq transport and SCRAM/channel-binding acceptance remain a
separate test after scoped credentials exist.

CA maintenance should record a warning 30 days before the earliest configured
root/observed server expiry, stop new admission at expiry, and leave unresolved
original commands visible. These are proposed operator bounds, not an implemented
monitor. Replace CA material only from a freshly verified exact-project download;
re-run hostname/TLS and scoped read-only canaries before promotion. Review
overlapping bundles explicitly; do not accept an arbitrary old root indefinitely.
There is currently no reviewed CRL/OCSP policy; do not claim revocation validation.

## Credential issuance, storage and acceptance plan

**Important missing proof:** the C1/C2 fixture creates logins with its disposable
superuser before exercising non-admin sessions. It proves authentication and
scope denial, not that hosted `postgres` can securely issue/grant/revoke the whole
credential pair. C3B must rehearse issuance as the actual hosted-like limited
`postgres`, including creator ADMIN/SET/INHERIT membership behavior, default
privileges and private-owner registry insertion. Do not copy the fixture issuer
into production or borrow `supabase_admin`/managed credentials. If the limited
issuer cannot complete the exact procedure, stop and redesign/review that boundary.

The intended acceptance order after complete-package review is:

1. Reverify target identity, reviewed package/catalog hashes and required role
   ownership. Establish closed worker admission; reserve exact Auth owner and
   run UUIDs without creating economic activity. Never derive owner from an
   unauthenticated request or a service-role owner argument.
2. Prepare two new independent `vn_native_<32 lowercase hex>` principals, separate
   issuance UUIDs and cryptographically random passwords in memory. Require
   NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOINHERIT/NOREPLICATION/NOBYPASSRLS, one or
   two connection slots each, exactly one ADMIN FALSE/INHERIT FALSE/SET TRUE
   capability membership, and immutable OID/name/owner/run binding. Unexpected
   role/name/OID collision or inherited access fails closed. Login creation,
   membership and binding must be one reviewed bounded atomic procedure; no
   window may expose unbound active authority.
3. Keep writes <=2 hours and original-ID economic recovery <=24 hours from
   issuance, matching the existing SQL ceilings. Finite `VALID UNTIL` covers
   write expiry and cannot exceed recovery expiry. Use database UTC for authority;
   an operator clock does not extend it. Scheduled rotation is not yet implemented.
4. Stage secrets only in the exact selected worker service's private store and
   expose them through a reviewed explicit in-process credential loader. Do not
   place passwords in argv, URLs, Git, PRs, CLI output, shared shell startup,
   Vercel frontend variables or an environment dump. Current startup still uses
   the legacy environment path; installing secrets does not select C2. The native
   command writer must not retain a broad service-role fallback. Auth-verification
   keys and provider keys are separate scoped inputs with shared-account quota
   coordination, not authority to write command tables.
5. Before any command, use each actual native login through the C2 configuration
   for one bounded **read-only** canary: real TCP/TLS/SCRAM/channel binding, exact
   `session_user`/`system_user`, one capability's attributes/membership, effective
   limits and expected original run state. Prove wrong owner/run/other capability
   are refused in the isolated rehearsal; do not invent a test run in production.
   A valid TLS-only probe or the management metadata above does not pass this step.
6. After reviewed migration/two-owner/overlap/rollback acceptance, enable only the
   reviewed selected service with one fenced controller and one serialized pair.
   Measure handshake/statement/COMMIT/relay tails and aggregate connection usage
   under provider traffic before choosing a cadence. Current 0.5-second connect
   default and server maximum of 60 are not measured throughput guarantees.

Rotation means a fresh immutable pair bound to the same exact owner/run and new
issuance IDs. Close admission, drain owned operations, preserve unresolved original
command IDs, validate new read-only access, then revoke old bindings and remove
only the old secret versions. An uncertain command must be reconciled through its
original ID/request; do not issue a fresh mutation to compensate for a lost reply.
Credential revocation is irreversible for that issuance; rollback uses newly
reviewed credentials rather than undoing revocation.

Emergency revocation must close worker admission and perform one-way registry
revocation with a finite lock/statement budget. The existing `FOR SHARE` admission
lock means revocation waits for admitted transactions; timeout is not success.
`NOLOGIN`, password expiry or password rotation alone do not disable open-session
authority. A separately reviewed incident procedure may terminate **only exact
issued principal/PID sessions** after identity verification; no broad process,
role or shared credential cleanup is permitted. Independently prove revocation
and no new admission before reporting success. Keep journal/projections/bindings
as reconciliation/audit evidence. [Existing native authorization contract](NATIVE-SESSION-AUTH.md).

Additive rollback closes the new writer, drains/reconciles admitted original
commands, revokes only the scoped credentials and keeps acknowledged economics,
positions, projections and historical reads. Do not drop the new schema/history,
reenable an unfenced legacy writer or silently resume a former worker. Production
DDL composition and this post-acknowledgment rollback still need B2/A3 rehearsal.
This inert preflight release itself needs only a reviewed code revert.

## Hosting dependency and remaining substantial research

The current direct endpoint requires outbound IPv6. Railway now documents a
per-service opt-in IPv6 switch, disabled by default. That makes it the leading
candidate for the first supervised worker, subject to actual service/region
reachability, budget and operational acceptance. No host is provisioned here.
Supabase's compatibility table still lists Railway as IPv4-only; the provider's
new explicit outbound support is the more specific current source. Render needs
a separately reviewed IPv4 alternative; neither an automatic session-pooler
fallback nor a paid Supabase add-on is included. [Railway outbound networking](https://docs.railway.com/networking/outbound-networking),
[Supabase compatibility](https://supabase.com/docs/guides/troubleshooting/supabase--your-network-ipv4-and-ipv6-compatibility-cHe3BP),
[full hosting review](../../WORKER-HOSTING-RESEARCH.md).

Keep C3 open until the CA, actual worker network, limited issuer and real scoped
connection canary are accepted. Pull deeper research forward for CA provenance/
expiry/revocation, bundled libpq/OpenSSL/SBOM/license/security maintenance, direct
handshake/COMMIT/relay tails and aggregate slot usage, pooler backend identity/
channel binding/queue limits, and finite revocation-lock latency. Then finish
durable legacy drain/reconciliation/archive evidence/invalidation, full forward
composition/history/catalog/overlap and additive rollback, followed by D3C/A3
service/browser/hosted acceptance. No live wallet operations are authorized.
