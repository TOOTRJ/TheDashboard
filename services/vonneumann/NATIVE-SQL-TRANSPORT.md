# B2C2: owned native async SQL transport

Reviewed 2026-10-06. This component is explicitly injected and inert. It is not
selected by the service, a hosted credential issuer, or a deployed migration.
The prior [native authentication candidate](NATIVE-SESSION-AUTH.md) and unchanged
canonical v5 package remain outside `supabase/migrations` and startup.

## Driver decision and boundaries

`psycopg[binary]==3.3.6` is exact-pinned in both hash locks. The existing 49
package versions are preserved; only Psycopg and psycopg-binary are added.
CPython 3.12.14 clean hash installations work on Darwin ARM64 and Linux ARM64.
The tested binary wrapper bundles libpq 18.6. The transport requires the binary
implementation and libpq >=17; the actual server must be PostgreSQL 17.

Psycopg supplies explicit asynchronous connections and transaction completion;
its bundled libpq exposes `require_auth`, `channel_binding` and client-certificate
controls. This fits the current SCRAM actor contract. Asyncpg was considered,
but its documented connection interface does not expose the same channel-binding
control. That is a decision for this constrained adapter, not a performance
benchmark or a claim that one driver is universally better. The documentation
site currently serves a 3.3.7 development build; tests execute pinned 3.3.6.
[Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html),
[async operations](https://www.psycopg.org/psycopg3/docs/advanced/async.html),
[libpq connection parameters](https://www.postgresql.org/docs/18/libpq-connect.html),
[asyncpg connection API](https://magicstack.github.io/asyncpg/current/api/index.html).

The runtime makes no shell/psql calls and accepts no DSN, arbitrary SQL, hostname,
port, database, pooler, environment credential, application config or public
client. Private caller-injected credentials and CA bytes are required. The host
is `db.fxpxsciltakyypunglzr.supabase.co`, port 5432, database postgres. DNS picks
one public IPv4/IPv6 address under the connect/whole deadline; `hostaddr` binds the
connection to that address while the canonical hostname supplies TLS verification
and SNI. There is no address, profile or submission retry.

Each adapter pins one canonical owner/run and one capability. Native usernames
must match the reviewed issuance namespace. A pair requires different economic
and relay principals, routes the five economic and three relay entrypoints, and
refuses concurrent operations across both. Server-side issuance checks still
establish authority independently of constructor claims. No raw table/helper/read
function is exposed by this transport.

## TLS and ambient configuration

Explicit `verify-full`, supplied CA, minimum TLS 1.2, required SCRAM and required
channel binding fail closed. Client certificates and GSS encryption are disabled.
Passwords are passed only in memory, never a file, command argument or repr.
Any inherited environment name beginning `PG` causes refusal; no other process's
environment is changed. `passfile`, certificate/key and CRL parameters explicitly
prevent default home-directory lookup. The temporary public CA file lives in a
private mode-700 owned directory, is mode 600 and is removed after connection/task
cleanup. System trust roots are not loaded.

Real tests found that setting an **empty existing CRL directory enables CRL
checks**, which fails for a CA without a CRL. The final adapter sets an explicitly
absent CRL file in its owned directory and no CRL directory. This suppresses shared
home-file fallback without claiming revocation-list validation. libpq's source
explains the behavior; the actual driver test exercises the corrected parameters.
[OpenSSL initialization in PostgreSQL 18](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/interfaces/libpq/fe-secure-openssl.c).
Hosted CA acquisition, expiry/replacement and certificate revocation policy still
require B2C3 review before provisioning or runtime selection.

## One owned transaction and exact responses

1. Validate the fixed RPC signature, owner/run, UUIDs, integer/decimal strings,
   JSON shape/depth/node/byte bounds, and take immutable parameter snapshots before
   the first await. Bind values with explicit casts; callers cannot supply SQL.
2. Open one fresh owned connection with autocommit enabled only to allow explicit
   transaction management, no prepared statements, no pool or shared transaction.
   Startup options pin search_path, synchronous_commit and server timeouts.
3. Explicitly BEGIN, SET LOCAL ROLE to the chosen non-admin capability, and call
   the schema-pinned RPC exactly once in a materialized query.
4. Return capped raw UTF-8 bytea, decode strict JSON and reject duplicate keys,
   fractions/nonfinite numbers, invalid/deep JSON, oversized or unexpected shapes.
   Money remains decimal strings; large JSON integers are preserved. A legitimate
   SQL NULL is accepted only for original-command readback.
5. Explicitly COMMIT. A receipt is returned only after COMMIT status and idle
   transaction status are confirmed, the whole deadline is still valid, and
   connection/task cleanup succeeds.

Request cap is 327,680 bytes; result cap is 393,216 bytes with the existing strict
40,000-node/64-depth contract. The query limits the RPC result transmitted over
the wire; this is not a defense against a malicious PostgreSQL server emitting
unbounded protocol errors, nor a server-allocation bound. The trusted reviewed
SQL contract and finite server timeouts remain necessary.

| Bound | Default | Meaning |
|---|---:|---|
| Whole operation | 3 s | Connect through validated confirmed COMMIT |
| Connect phase | 0.5 s | DNS plus TLS/SCRAM connection |
| Statement phase | 1.5 s | BEGIN, role, one RPC and fetch phases |
| COMMIT phase | 0.5 s | Explicit acknowledgment of transaction end |
| Cleanup | 1 s | Owned connection close and retained task drain |

All bounds must be finite, positive and at most 15 seconds; connect/statement/
commit phases cannot exceed the whole operation. Server statement/lock limits
match the statement bound; idle-in-transaction and transaction limits match the
whole bound. These are conservative testable defaults, not measured hosted
latency guarantees or proof of a one-second paper cadence. Async deadlines depend
on event-loop cooperation; process suspension or synchronous work can delay them.

Caller cancellation cannot cancel an admitted owned transaction. I/O tasks,
including a connection returned after its phase timeout, remain retained until
drained/closed. Pending or failed cleanup latches admission closed; later work
cannot silently reuse it. Closing a pair owns both child closures even if its
caller cancels. Driver diagnostics, SQL, parameters and credentials are suppressed
from public transport errors; no logging of those values is added.

A missing, cancelled or late COMMIT reply may still represent a durable command.
There are no mutation retries. The existing CommandRepository keeps the original
prepared ID/request and resolves it read-only; the complete stored request and
receipt must match. A missing journal entry or unavailable run remains uncertain
and does not authorize a replacement command. Psycopg's cancellation guidance
likewise warns that cancellation is not evidence the operation did not finish.
[Cancellation guidance](https://www.psycopg.org/psycopg3/docs/advanced/async.html#interrupting-async-operations).

## Real offline acceptance

Fourteen ordinary tests cover parameter snapshots, injection/owner/run/capability
refusal, strict/capped/NULL results, explicit commit order, cancellation, commit
timeout, late connection cleanup, cleanup failure, ambient/loop denial, sanitized
diagnostics, pair routing and invalid credentials/CA/bounds.

Eight real driver cases execute in a uniquely owned nonroot Linux container
sharing only the owned PostgreSQL fixture's **network-none** namespace. Neither
container publishes ports or mounts host files. Source `.py` files, the reviewed
lock and explicitly supplied hash-verified wheels are staged through stdin;
installation is offline. Synthetic CA/observer secrets stay in owned private
tmpfs. The Python tmpfs permits executable library mappings for the binary
wheels; the image root is read-only, privileges/capabilities are dropped and
CPU/memory/PID bounds apply. Cached image IDs are pinned per run; the harness
never installs Docker or downloads an image. Cleanup verifies each exact
ownership label before removing only its own container.

Only private DNS resolution is patched to fixture loopback. The driver, hostname
verification, CA, SCRAM/channel binding, SQL, roles, controller, repository and
durable publisher are real. Jupiter/Birdeye/RPC responses are synthetic wire
fixtures parsed by the actual adapters; no provider or hosted database is called.
Independent fixture observer sessions prove committed or rolled-back state.

- Complete bootstrap, exact fractional-price paper tick, pause, reserved stop,
  eight latest probe projections, durable event acceptance and drained outbox.
- A lost reply injected after a real bootstrap COMMIT resolves/installs the
  original ID without a duplicate journal or provider refetch.
- Caller cancellation after a real COMMIT retains ownership and blocks overlap
  until its original reply is settled.
- A real SQL lock timeout and pre-COMMIT failure leave no created run/journal;
  reconciliation remains uncertain rather than admitting a fresh command.
- A reply timeout after a real COMMIT leaves one durable journal entry and
  read-only original-ID recovery succeeds.
- Actual bad CA/password and forged owner/run/capability fail closed; a legitimate
  missing journal read on an existing run returns SQL NULL.

Fault hooks delay/drop the reply around actual driver COMMIT, not a network proxy
or replacement database. This does not prove every operating-system packet-loss
or hosted pooler failure mode. Ordinary tests and real acceptance both pass under
the new hash lock. Full regression and release evidence are recorded in
configuration section 55 and the PR.

To repeat, use a clean isolated Python environment installed with
`pip --isolated install --require-hashes -r requirements-dev.txt`, both reviewed
cached images, and an absolute directory containing CPython 3.12 wheels for the
selected Linux architecture downloaded with `--require-hashes --only-binary=:all:`.
Then from `services/vonneumann`, with dotenv/bytecode disabled:

```sh
DASHBOARD_ISOLATED_POSTGRES_TESTS=1 \
DASHBOARD_NATIVE_SQL_WHEELS=/absolute/task-owned/linux-wheels \
PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 \
/absolute/task-owned/venv/bin/python -m unittest tests.postgres.test_native_sql -v
```

## Remaining ordered gates and research

1. **B2C3 hosted profile/credential plan:** reverify exact Dashboard metadata and
   capture read-only actual CA/SSL, role/auth and connection facts. Prove chosen
   worker host has direct IPv6 reachability, or separately rehearse a session
   pooler's backend identity, TLS/channel binding, timeout/queue behavior and
   custom-role routing. Do not substitute a pooler just because port 5432 matches.
   Supabase recommends direct connections for persistent IPv6 backends and a
   shared session pooler for IPv4-only backends; its pooled username differs.
   This adapter deliberately supports only direct connections today.
   [Supabase connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres).
2. Prepare exact-role private-secret issuance/storage/expiry/rotation/revocation,
   bounded credential validation and additive rollback. No hosted role or secret
   has been provisioned. **Deep substantial research:** CA lifetime/revocation,
   native-library updates/SBOM/licensing, connection/handshake capacity, phase
   latency, held transaction/revocation locks, aggregate quotas and lease headroom.
   Fresh connections favor clear ownership now; pooling requires measured evidence
   and an equally strong reset/ownership/capability proof before adoption.
3. Finish B2 durable owner/run/original-ID/provenance-bound legacy drain,
   reconciliation/archive evidence and invalidation; compose canonical v5/auth/
   retirement/classifier with migration history/locks/old-worker overlap and
   additive rollback retaining already acknowledged commands.
4. D3C/A3 selected service and compatible browser controls/history/archive/replay,
   two-user full-flow acceptance, then verified hosted cutover. Operational
   timing/quotas, preview isolation, worker packaging/hosting and a bounded paper
   pilot remain separate acceptance gates.

This release needs only a reviewed code revert for rollback. Production SQL,
credentials and runtime selection are unchanged. Live wallet funding, signing,
swaps and trading are outside authorization.
