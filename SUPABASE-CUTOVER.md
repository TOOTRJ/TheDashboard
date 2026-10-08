# Reviewed Dashboard-only closed database cutover

2026-10-07. The user confirmed no other known direct database clients and
authorized necessary migrations and data changes only in **The Dashboard**.
The separate Claude project and shared account/tool configuration stay outside
this operation. The worker stays closed and credential-free until its separate
native-session and hosted paper acceptance.

## Maintenance and managed findings

Exact GitHub, Vercel, Supabase and Railway identity checks pass. Database SSL
enforcement was enabled on `fxpxsciltakyypunglzr`, under organization
`cqfnnaunmupdyobkyqfo`; its applied status and post-reboot management/TLS and four
production dashboard HTTP checks pass. No migration contents or legacy grants
changed during maintenance. The known internal Auth connection is not an
external application client. [Supabase SSL maintenance behavior](https://supabase.com/docs/guides/platform/ssl-enforcement).

Actual managed rollback rehearsals found and repaired three gaps:

1. The existing installer `postgres` has REPLICATION. The earlier capture omitted
   this attribute and the synthetic installer incorrectly had NOREPLICATION.
   The installer now requires the complete measured profile. Newly created
   worker/capability/owner roles still explicitly forbid replication and admin
   privileges. No existing role attribute was changed.
2. Managed `auth.uid()` already grants PUBLIC EXECUTE, while the private owner
   has no Auth schema USAGE. Function privilege alone is not usable access.
   Preserve this managed ACL; reject schema access, grant options and references,
   and retain the installer-owned narrow identity bridge. Real fixture tests
   prove a direct `auth.uid()` call remains denied. No managed Auth grants change.
3. Standalone metadata deparsing used the session's public/extensions search path,
   while the install oracle uses pg_catalog/pg_temp. Identical FK/trigger definitions
   looked different. The standalone audit now uses the oracle's fixed path; a
   real PostgreSQL test independently compares both complete capture results.

The complete managed installer, issuer and production/history wrapper each pass
in a transaction ending in ROLLBACK. Separate reads confirm no new schema, owner,
native login or migration remains after those canaries. This does not prove a
committed credential's actual Railway SCRAM/channel-binding session.

## Explicit production wrapper

`services/vonneumann/db-contract/forward/production.py` is an offline builder for
the new `20261007010000_vonneumann_closed_v5.sql`. Its inputs are the hash-pinned
complete package and independently captured, committed metadata review. It
does not import test fixtures or access a database. The generated transaction
requires exact reviewed history/catalog values under locks, enforces a 25-second
transaction deadline, creates the canonical private schemas/roles, retires the
old direct writers and verifies all final objects. It finishes closed with zero
native bindings and zero new runs. It exposes no API schema and opens no worker.

The existing historical local migration edit is excluded from this operation.
Do not use a blanket `db push` to perform the cutover.

`python3 scripts/dashboard-db-cutover.py verify` is read-only. It rechecks the
dedicated GitHub identity, resolved dedicated Vercel project/profile and immutable
repository/team link, exact Supabase project/org/local link/applied SSL setting,
and exact closed Railway service/token scope. Responses and environment values
are never dumped. `preflight` additionally requires the exact migration in
fetched `origin/main`, matching fresh independent history/catalog and the owned,
mode-0600 private snapshot. The snapshot contains the five existing bot tables,
original migration history and metadata; it is not a whole Auth/database backup.
It is in the ignored `ssl/maintenance-20261007/` directory.

Only explicit `apply` can submit this one migration. It first persists an original
operation UUID, source hash and target review in a private exclusive file. The
exact full migration source is inserted into migration history before the same
COMMIT, with no password/connection URL or credential issuance. Application and
history cannot commit separately. The Management API client has a finite outer
deadline; a lost or rejected reply is not automatically retried.

`reconcile` checks the original hash/target/version, complete catalog in a fresh
read-only session, exact history source and closed release/epoch in separate
fresh sessions. A failed reconciliation retains the original unknown outcome.
Never delete that record or substitute a fresh operation to bypass uncertainty.

## Recovery and later activation

Before COMMIT, an error/deadline rolls back the transaction, including old grant
changes, new objects and history. A confirmed closed install can remain inert
while acceptance continues. Diagnose any postflight failure with the exact
original record; do not repeat the installer or drop new ledgers.

After acknowledged economics, close browser/process admission and drain owned
operations, then use the original reviewed request ID and evidence hash for the
private `vn_release.transition(...,'retired',...)`. Retain economics, holdings,
checkpoints, journals, outbox/relay, legacy data and reviews. Do not restore old
writers or invent liquidation proceeds. The complete forward contract documents
lock/epoch/readback behavior and one-way retirement.

Next: committed managed verification; private finite native credentials and
actual Railway TLS/SCRAM/channel binding/scope/expiry/revocation; owner-only
`vn_read` exposure and two-user hosted browser acceptance; provider/SQL/COMMIT/
relay/lease/quota/resource/interruption/overlap measurements; then the finite
two-gene, eight-candidate SOL/USD paper pilot within the approved budget.
Deep substantial research remains on managed hooks, secret/issuer log handling,
credential rotation, real latency tails, shared provider billing/quota and
retention/compact checkpoints. No live wallet/signing/swaps are included.
